"""Circuit Breaker pattern implementation for external service protection.

This module provides a robust circuit breaker implementation to prevent cascading
failures when external services (Spotify API, ClamAV, etc.) become unavailable.

States:
    CLOSED: Normal operation, requests pass through
    OPEN: Service unavailable, requests fail fast
    HALF_OPEN: Recovery phase, limited requests allowed to test service health
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states following the standard pattern."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a request is blocked due to open circuit breaker."""

    def __init__(
        self,
        service_name: str,
        *,
        remaining_seconds: float,
        failure_count: int,
    ) -> None:
        self.service_name = service_name
        self.remaining_seconds = remaining_seconds
        self.failure_count = failure_count
        super().__init__(
            f"Circuit breaker for '{service_name}' is open. "
            f"Recovery in {remaining_seconds:.1f}s after {failure_count} failures."
        )


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of failures before opening the circuit.
        recovery_timeout_seconds: Time to wait before attempting recovery.
        success_threshold: Successful calls needed in HALF_OPEN to close circuit.
        excluded_exceptions: Exception types that don't count as failures.
    """

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    success_threshold: int = 2
    excluded_exceptions: tuple[type[Exception], ...] = ()


@dataclass
class CircuitBreakerMetrics:
    """Metrics for observability integration."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_transitions: int = 0


@dataclass
class _CircuitState:
    """Internal mutable state for circuit breaker."""

    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change_time: float = field(default_factory=time.monotonic)
    active_probe_count: int = 0  # number of concurrent HALF_OPEN probes in flight
    active_probe_owners: set[asyncio.Task[Any]] = field(default_factory=set)


class CircuitBreaker:
    """Async-safe circuit breaker with configurable thresholds.

    Usage:
        circuit = CircuitBreaker("spotify", config=CircuitBreakerConfig())

        async with circuit:
            response = await external_api_call()

    The circuit breaker will:
    1. Allow calls when CLOSED
    2. Track failures and open when threshold is reached
    3. Reject calls immediately when OPEN (fail fast)
    4. Allow limited calls when HALF_OPEN to test recovery
    5. Close again after successful recovery

    State mutations use a thread lock because a registered breaker may be shared
    by callers running on different event loops. Lock waits remain cancellable,
    and the protected mutations never await.
    """

    __slots__ = (
        "_config",
        "_internal_state",
        "_lock",
        "_metrics",
        "_on_state_change",
        "_service_name",
        "_state_waiters",
        "_state_waiters_lock",
    )

    def __init__(
        self,
        service_name: str,
        *,
        config: CircuitBreakerConfig | None = None,
        on_state_change: (
            Callable[[str, CircuitBreakerState, CircuitBreakerState], None] | None
        ) = None,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            service_name: Identifier for the protected service (used in logs/metrics).
            config: Configuration parameters. Defaults to sensible values.
            on_state_change: Optional callback invoked on state transitions.
        """
        self._service_name = service_name
        self._config = config or CircuitBreakerConfig()
        self._internal_state = _CircuitState()
        self._lock = threading.Lock()
        self._state_waiters_lock = threading.Lock()
        self._state_waiters: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]
        ] = []
        self._metrics = CircuitBreakerMetrics()
        self._on_state_change = on_state_change
        # MED-W19: _in_half_open_probe removed — probe ownership is tracked
        # exclusively via _internal_state.active_probe_count (incremented/
        # decremented while self._lock is held), eliminating the shared boolean
        # that could be clobbered by a concurrent caller between lock acquisitions.

    @property
    def service_name(self) -> str:
        """Name of the protected service."""
        return self._service_name

    async def _acquire_state_lock(self) -> None:
        """Wait on cross-loop notifications without blocking or polling this loop."""
        loop = asyncio.get_running_loop()
        while True:
            with self._state_waiters_lock:
                if self._lock.acquire(blocking=False):
                    return
                waiter = loop.create_future()
                self._state_waiters.append((loop, waiter))

            try:
                await waiter
            except asyncio.CancelledError:
                with self._state_waiters_lock:
                    self._state_waiters = [
                        entry for entry in self._state_waiters if entry[1] is not waiter
                    ]
                raise

    def _release_state_lock(self) -> None:
        """Release state and wake queued loops without awaiting under the lock."""
        with self._state_waiters_lock:
            self._lock.release()
            waiters = tuple(self._state_waiters)
            self._state_waiters.clear()

        for loop, waiter in waiters:
            try:
                loop.call_soon_threadsafe(self._wake_state_waiter, waiter)
            except RuntimeError:
                # A waiter may belong to a loop that was closed during shutdown.
                continue

    @staticmethod
    def _wake_state_waiter(waiter: asyncio.Future[None]) -> None:
        if not waiter.done():
            waiter.set_result(None)

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        return self._internal_state.state

    @property
    def failure_count(self) -> int:
        """Current consecutive failure count."""
        return self._internal_state.failure_count

    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Metrics snapshot for observability."""
        return self._metrics

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state with logging and callback."""
        from app.core.metrics import (
            record_circuit_breaker_state,
            record_circuit_breaker_trip,
        )

        old_state = self._internal_state.state
        if old_state == new_state:
            return

        self._internal_state.state = new_state
        self._internal_state.last_state_change_time = time.monotonic()
        self._metrics.state_transitions += 1

        # Record metrics
        record_circuit_breaker_state(self._service_name, new_state.value)
        if new_state == CircuitBreakerState.OPEN:
            record_circuit_breaker_trip(self._service_name)

        logger.info(
            "Circuit breaker state transition",
            extra={
                "event": "circuit_breaker_transition",
                "service": self._service_name,
                "from_state": old_state.value,
                "to_state": new_state.value,
                "failure_count": self._internal_state.failure_count,
            },
        )

        if self._on_state_change:
            try:
                self._on_state_change(self._service_name, old_state, new_state)
            except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — callback failure must not crash circuit breaker (reviewed TD-27-04)
                logger.warning(
                    "Circuit breaker state change callback failed",
                    exc_info=True,
                    extra={"service": self._service_name},
                )

    def _should_allow_request(self) -> bool:
        """Determine if a request should be allowed based on current state."""
        state = self._internal_state

        if state.state == CircuitBreakerState.CLOSED:
            return True

        if state.state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - state.last_failure_time
            if elapsed >= self._config.recovery_timeout_seconds:
                self._transition_to(CircuitBreakerState.HALF_OPEN)
                state.success_count = 0
                state.active_probe_count = len(state.active_probe_owners)
                return state.active_probe_count == 0
            return False

        # HALF_OPEN: allow exactly one concurrent probe; queue the rest as rejected.
        # active_probe_count is incremented in __aenter__ (under the same lock) so
        # the second concurrent caller sees count==1 and is rejected before we release.
        return state.active_probe_count == 0

    def _get_remaining_open_time(self) -> float:
        """Get remaining time until recovery attempt."""
        elapsed = time.monotonic() - self._internal_state.last_failure_time
        remaining = self._config.recovery_timeout_seconds - elapsed
        return max(0.0, remaining)

    def _record_success(self, *, probe_owner: bool = False) -> None:
        """Record a successful call and advance HALF_OPEN only for its probe."""
        self._metrics.total_calls += 1
        self._metrics.successful_calls += 1
        state = self._internal_state

        if state.state == CircuitBreakerState.HALF_OPEN:
            # A CLOSED request may still be in flight when another request trips
            # the breaker. Its late success is a metric, not a recovery probe.
            if not probe_owner:
                return
            state.success_count += 1
            if state.success_count >= self._config.success_threshold:
                self._transition_to(CircuitBreakerState.CLOSED)
                state.failure_count = 0
                state.success_count = 0
        elif state.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success in closed state
            state.failure_count = 0

    def _record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        self._metrics.total_calls += 1
        self._metrics.failed_calls += 1

        # Check if this exception should be excluded from failure counting
        if isinstance(exception, self._config.excluded_exceptions):
            logger.debug(
                "Circuit breaker ignoring excluded exception",
                extra={
                    "service": self._service_name,
                    "exception_type": type(exception).__name__,
                },
            )
            return

        state = self._internal_state
        state.failure_count += 1
        state.last_failure_time = time.monotonic()

        if state.state == CircuitBreakerState.HALF_OPEN:
            # Any failure in HALF_OPEN reopens the circuit
            self._transition_to(CircuitBreakerState.OPEN)
        elif state.state == CircuitBreakerState.CLOSED:
            if state.failure_count >= self._config.failure_threshold:
                self._transition_to(CircuitBreakerState.OPEN)

    async def __aenter__(self) -> CircuitBreaker:
        """Enter the circuit breaker context."""
        await self._acquire_state_lock()
        try:
            if not self._should_allow_request():
                self._metrics.rejected_calls += 1
                raise CircuitBreakerOpenError(
                    self._service_name,
                    remaining_seconds=self._get_remaining_open_time(),
                    failure_count=self._internal_state.failure_count,
                )
            # MED-W19: Claim the single HALF_OPEN probe slot atomically while the
            # lock is held. Track the owning task so a CLOSED request that exits
            # after a state transition cannot release another request's permit.
            if self._internal_state.state == CircuitBreakerState.HALF_OPEN:
                current_task = asyncio.current_task()
                if current_task is None:
                    raise RuntimeError("circuit breaker probe requires an asyncio task")
                self._internal_state.active_probe_owners.add(current_task)
                self._internal_state.active_probe_count = len(
                    self._internal_state.active_probe_owners
                )
            return self
        finally:
            self._release_state_lock()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Exit the circuit breaker context."""
        cancelled_during_acquire = False
        while True:
            try:
                await self._acquire_state_lock()
                break
            except asyncio.CancelledError:
                # A repeated cancel must not strand a HALF_OPEN reservation.
                # _acquire_state_lock removes the cancelled waiter; retry without
                # polling, then propagate cancellation after state cleanup.
                cancelled_during_acquire = True

        try:
            # Release only a HALF_OPEN slot owned by this context's task. Other
            # CLOSED calls may still be in flight after the breaker transitions.
            current_task = asyncio.current_task()
            probe_owner = (
                current_task is not None
                and current_task in self._internal_state.active_probe_owners
            )
            if current_task is not None and probe_owner:
                self._internal_state.active_probe_owners.remove(current_task)
                self._internal_state.active_probe_count = len(
                    self._internal_state.active_probe_owners
                )
            if exc_val is None:
                self._record_success(probe_owner=probe_owner)
            elif isinstance(exc_val, Exception):
                self._record_failure(exc_val)
        finally:
            self._release_state_lock()
        if cancelled_during_acquire:
            raise asyncio.CancelledError
        # Don't suppress exceptions
        return False

    async def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        await self._acquire_state_lock()
        try:
            self._transition_to(CircuitBreakerState.CLOSED)
            self._internal_state.failure_count = 0
            self._internal_state.success_count = 0
            logger.info(
                "Circuit breaker manually reset",
                extra={"service": self._service_name},
            )
        finally:
            self._release_state_lock()

    async def force_open(self) -> None:
        """Manually open the circuit breaker."""
        await self._acquire_state_lock()
        try:
            self._transition_to(CircuitBreakerState.OPEN)
            self._internal_state.last_failure_time = time.monotonic()
            logger.warning(
                "Circuit breaker manually opened",
                extra={"service": self._service_name},
            )
        finally:
            self._release_state_lock()


# Registry for global circuit breaker instances
_circuit_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def _get_registry_lock() -> threading.Lock:
    """Return the thread lock protecting synchronous registry access."""
    return _registry_lock


async def get_circuit_breaker(
    service_name: str,
    *,
    config: CircuitBreakerConfig | None = None,
    on_state_change: (
        Callable[[str, CircuitBreakerState, CircuitBreakerState], None] | None
    ) = None,
) -> CircuitBreaker:
    """Get or create a circuit breaker for the specified service.

    This ensures a single circuit breaker instance per service name across
    the application, maintaining consistent state tracking.

    Args:
        service_name: Unique identifier for the service.
        config: Configuration (only used when creating new instance).
        on_state_change: Callback for state transitions.

    Returns:
        CircuitBreaker instance for the service.
    """
    with _get_registry_lock():
        if service_name not in _circuit_breakers:
            _circuit_breakers[service_name] = CircuitBreaker(
                service_name,
                config=config,
                on_state_change=on_state_change,
            )
        return _circuit_breakers[service_name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers for metrics collection."""
    with _get_registry_lock():
        return dict(_circuit_breakers)


async def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers. Useful for testing."""
    with _get_registry_lock():
        breakers = tuple(_circuit_breakers.values())

    for breaker in breakers:
        await breaker.reset()
