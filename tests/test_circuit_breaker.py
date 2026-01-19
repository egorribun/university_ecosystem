"""Unit tests for circuit breaker implementation."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    _circuit_breakers,
    get_all_circuit_breakers,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    async def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker("test_initial")
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_transitions_to_open_after_threshold_failures(self):
        """Circuit opens after reaching failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test_open", config=config)

        for _ in range(3):
            try:
                async with breaker:
                    raise ValueError("simulated failure")
            except ValueError:
                pass

        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 3

    async def test_open_circuit_rejects_requests(self):
        """Open circuit rejects requests immediately."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=60)
        breaker = CircuitBreaker("test_reject", config=config)

        # Trigger circuit open
        try:
            async with breaker:
                raise RuntimeError("failure")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN

        # Next request should be rejected
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            async with breaker:
                pass

        assert exc_info.value.service_name == "test_reject"
        assert exc_info.value.remaining_seconds > 0

    async def test_transitions_to_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=0.1,  # Short timeout for testing
            success_threshold=1,  # Single success closes the circuit
        )
        breaker = CircuitBreaker("test_half_open", config=config)

        # Trigger circuit open
        try:
            async with breaker:
                raise RuntimeError("failure")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Next request should be allowed (HALF_OPEN)
        async with breaker:
            pass

        # Should now be CLOSED after success
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_half_open_closes_after_success_threshold(self):
        """Circuit closes after success threshold in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=0.05,
            success_threshold=3,  # Need 3 successes to close
        )
        breaker = CircuitBreaker("test_close", config=config)

        # Trigger circuit open
        try:
            async with breaker:
                raise RuntimeError("failure")
        except RuntimeError:
            pass

        await asyncio.sleep(0.1)

        # First success - should transition to HALF_OPEN on entry, still HALF_OPEN
        async with breaker:
            pass
        # After first success, state is HALF_OPEN (success_count=1, need 3)
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Second success - still HALF_OPEN
        async with breaker:
            pass
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Third success - should close
        async with breaker:
            pass
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_half_open_reopens_on_failure(self):
        """Circuit reopens immediately on failure in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=0.05,
            success_threshold=3,
        )
        breaker = CircuitBreaker("test_reopen", config=config)

        # Trigger circuit open
        try:
            async with breaker:
                raise RuntimeError("failure")
        except RuntimeError:
            pass

        await asyncio.sleep(0.1)

        # Failure in HALF_OPEN should reopen
        try:
            async with breaker:
                raise RuntimeError("another failure")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN


class TestCircuitBreakerConfig:
    """Tests for circuit breaker configuration."""

    async def test_default_config_values(self):
        """Default config has sensible values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.recovery_timeout_seconds == 30.0
        assert config.success_threshold == 2
        assert config.excluded_exceptions == ()

    async def test_excluded_exceptions_not_counted(self):
        """Excluded exceptions don't count toward failures."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            excluded_exceptions=(ValueError,),
        )
        breaker = CircuitBreaker("test_exclude", config=config)

        # These should not count
        for _ in range(5):
            try:
                async with breaker:
                    raise ValueError("excluded")
            except ValueError:
                pass

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

        # Non-excluded exceptions should count
        for _ in range(2):
            try:
                async with breaker:
                    raise RuntimeError("counted")
            except RuntimeError:
                pass

        assert breaker.state == CircuitBreakerState.OPEN


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics."""

    async def test_metrics_are_recorded(self):
        """Metrics are properly recorded."""
        breaker = CircuitBreaker("test_metrics")

        async with breaker:
            pass

        assert breaker.metrics.total_calls == 1
        assert breaker.metrics.successful_calls == 1
        assert breaker.metrics.failed_calls == 0

    async def test_failure_metrics_recorded(self):
        """Failed calls are recorded in metrics."""
        breaker = CircuitBreaker("test_failure_metrics")

        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        assert breaker.metrics.total_calls == 1
        assert breaker.metrics.failed_calls == 1

    async def test_rejected_calls_recorded(self):
        """Rejected calls (open circuit) are recorded."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test_rejected", config=config)

        # Trigger open
        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        # Try rejected call
        try:
            async with breaker:
                pass
        except CircuitBreakerOpenError:
            pass

        assert breaker.metrics.rejected_calls == 1


class TestCircuitBreakerRegistry:
    """Tests for global circuit breaker registry."""

    async def test_get_circuit_breaker_creates_new(self):
        """get_circuit_breaker creates new instance if not exists."""
        # Clean up any existing test breaker
        if "test_registry_new" in _circuit_breakers:
            del _circuit_breakers["test_registry_new"]

        breaker = await get_circuit_breaker("test_registry_new")
        assert breaker.service_name == "test_registry_new"

    async def test_get_circuit_breaker_returns_existing(self):
        """get_circuit_breaker returns existing instance."""
        breaker1 = await get_circuit_breaker("test_registry_existing")
        breaker2 = await get_circuit_breaker("test_registry_existing")
        assert breaker1 is breaker2

    async def test_get_all_circuit_breakers(self):
        """get_all_circuit_breakers returns all registered breakers."""
        await get_circuit_breaker("test_all_1")
        await get_circuit_breaker("test_all_2")

        all_breakers = get_all_circuit_breakers()
        assert "test_all_1" in all_breakers
        assert "test_all_2" in all_breakers

    async def test_reset_all_circuit_breakers(self):
        """reset_all_circuit_breakers resets all registered breakers."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = await get_circuit_breaker("test_reset_all", config=config)

        # Trigger open
        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN

        await reset_all_circuit_breakers()

        assert breaker.state == CircuitBreakerState.CLOSED


class TestCircuitBreakerManualControl:
    """Tests for manual circuit breaker control."""

    async def test_manual_reset(self):
        """Manual reset closes the circuit."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test_manual_reset", config=config)

        # Trigger open
        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN

        await breaker.reset()

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_manual_force_open(self):
        """Manual force_open opens the circuit."""
        breaker = CircuitBreaker("test_force_open")

        assert breaker.state == CircuitBreakerState.CLOSED

        await breaker.force_open()

        assert breaker.state == CircuitBreakerState.OPEN


class TestCircuitBreakerCallback:
    """Tests for state change callback."""

    async def test_callback_invoked_on_state_change(self):
        """Callback is invoked when state changes."""
        callback = MagicMock()
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker(
            "test_callback", config=config, on_state_change=callback
        )

        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        callback.assert_called_once_with(
            "test_callback",
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
        )

    async def test_callback_error_does_not_break_circuit(self):
        """Callback errors don't break circuit operation."""

        def failing_callback(*args):
            raise RuntimeError("callback failed")

        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker(
            "test_callback_error", config=config, on_state_change=failing_callback
        )

        # Should not raise despite callback error
        try:
            async with breaker:
                raise RuntimeError("fail")
        except RuntimeError:
            pass

        assert breaker.state == CircuitBreakerState.OPEN


class TestCircuitBreakerConcurrency:
    """Tests for concurrent access to circuit breaker."""

    async def test_concurrent_requests_handled_safely(self):
        """Concurrent requests are handled safely."""
        breaker = CircuitBreaker("test_concurrent")

        async def make_request():
            async with breaker:
                await asyncio.sleep(0.01)

        # Run multiple concurrent requests
        tasks = [asyncio.create_task(make_request()) for _ in range(10)]
        await asyncio.gather(*tasks)

        assert breaker.metrics.total_calls == 10
        assert breaker.metrics.successful_calls == 10

    async def test_concurrent_failures_handled_correctly(self):
        """Concurrent failures don't cause race conditions."""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = CircuitBreaker("test_concurrent_fail", config=config)

        async def fail_request():
            try:
                async with breaker:
                    await asyncio.sleep(0.01)
                    raise RuntimeError("fail")
            except RuntimeError:
                pass

        tasks = [asyncio.create_task(fail_request()) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Should have opened after threshold
        assert breaker.state == CircuitBreakerState.OPEN


class TestCircuitBreakerMetricsIntegration:
    """Tests for Prometheus metrics integration."""

    async def test_prometheus_metrics_recorded_on_transition(self):
        """Prometheus metrics are recorded on state transitions."""
        # Import the module to ensure metrics funcs are loaded first
        from app.core import metrics

        with (
            patch.object(metrics, "record_circuit_breaker_state") as mock_state,
            patch.object(metrics, "record_circuit_breaker_trip") as mock_trip,
        ):
            config = CircuitBreakerConfig(failure_threshold=1)
            breaker = CircuitBreaker("test_prometheus", config=config)

            try:
                async with breaker:
                    raise RuntimeError("fail")
            except RuntimeError:
                pass

            mock_state.assert_called_with("test_prometheus", "open")
            mock_trip.assert_called_with("test_prometheus")
