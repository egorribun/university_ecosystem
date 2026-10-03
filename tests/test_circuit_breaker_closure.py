"""Branch closure tests for circuit-breaker edge paths."""

import threading

import pytest

import app.core.circuit_breaker as circuit_module
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerState


def test_record_success_on_open_state_does_not_reset_failure_count() -> None:
    breaker = CircuitBreaker("edge-success")
    breaker._internal_state.state = CircuitBreakerState.OPEN
    breaker._internal_state.failure_count = 3

    breaker._record_success()

    assert breaker.failure_count == 3
    assert breaker.metrics.successful_calls == 1


@pytest.mark.asyncio
async def test_aexit_does_not_record_non_exception_base_exception() -> None:
    breaker = CircuitBreaker("edge-base-exception")
    sentinel = KeyboardInterrupt()

    result = await breaker.__aexit__(KeyboardInterrupt, sentinel, None)

    assert result is False
    assert breaker.metrics.total_calls == 0


def test_registry_lock_is_process_wide_and_thread_safe() -> None:
    first = circuit_module._get_registry_lock()
    second = circuit_module._get_registry_lock()

    assert first is second
    assert type(first) is type(threading.Lock())
