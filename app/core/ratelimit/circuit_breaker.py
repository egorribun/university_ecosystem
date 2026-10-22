"""PERF-30-01: Circuit breaker for Redis-backed rate limiting.

Three-state machine preventing cascading failures when Redis is unresponsive:
  CLOSED    → normal operation, forward to Redis
  OPEN      → skip Redis, return fallback immediately
  HALF_OPEN → allow one probe request; success→CLOSED, fail→OPEN (doubled timeout)

Thread-safe under Python 3.13+ free-threading via threading.Lock.
"""

import asyncio
import enum
import functools
import inspect
import threading
import time
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from prometheus_client import Counter, Gauge

from app.core.logging import get_logger

_log = get_logger(__name__)
_background_tasks: set[asyncio.Task[Any]] = set()

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

circuit_state_gauge = Gauge(
    "rate_limit_circuit_state",
    "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
)

circuit_transitions_total = Counter(
    "rate_limit_circuit_transitions_total",
    "Total circuit breaker state transitions",
    ["from_state", "to_state"],
)


class CircuitState(enum.IntEnum):
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


@dataclass(slots=True)
class CircuitAdmission:
    """One-shot request admission bound to the breaker state that issued it."""

    allowed: bool
    _owner: object = field(repr=False)
    _generation: int = field(repr=False)
    _state: CircuitState = field(repr=False)
    _force_open: bool = field(default=False, repr=False)
    _resolved: bool = field(default=False, repr=False)


class RedisCircuitBreaker:
    """Circuit breaker for Redis operations with exponential backoff recovery.

    Args:
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Initial seconds before transitioning OPEN → HALF_OPEN.
        max_recovery_timeout: Upper bound for exponential backoff.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        max_recovery_timeout: float = 300.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._base_recovery_timeout = recovery_timeout
        self._max_recovery_timeout = max_recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._current_recovery_timeout = recovery_timeout
        self._half_open_probe_sent = False  # RZ-33-11: single-probe gate
        self._admission_owner = object()
        self._state_generation = 0
        self._active_half_open_admission: CircuitAdmission | None = None
        self._lock = threading.RLock()
        self._state_listeners: list[
            Callable[[CircuitState, CircuitState], Awaitable[None] | None]
        ] = []

        circuit_state_gauge.set(CircuitState.CLOSED)

    # -- Public API --------------------------------------------------------

    def add_state_listener(
        self,
        listener: Callable[[CircuitState, CircuitState], Awaitable[None] | None],
    ) -> None:
        """Register a callback for circuit state transitions (old_state, new_state)."""
        with self._lock:
            if listener not in self._state_listeners:
                self._state_listeners.append(listener)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def allow_request(self) -> bool:
        """Return whether Redis should be attempted (legacy compatibility API)."""
        return self.admit_request().allowed

    def admit_request(self, *, force: bool = False) -> CircuitAdmission:
        """Admit a request and return a ticket for its eventual outcome.

        Ticketed outcomes are accepted only in the state generation that issued
        them. This prevents a late CLOSED request from resolving another
        request's HALF_OPEN probe.
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.CLOSED:
                return CircuitAdmission(
                    True,
                    self._admission_owner,
                    self._state_generation,
                    CircuitState.CLOSED,
                )
            if self._state == CircuitState.HALF_OPEN and not self._half_open_probe_sent:
                admission = CircuitAdmission(
                    True,
                    self._admission_owner,
                    self._state_generation,
                    CircuitState.HALF_OPEN,
                )
                self._half_open_probe_sent = True
                self._active_half_open_admission = admission
                return admission
            if self._state == CircuitState.OPEN and force:
                return CircuitAdmission(
                    True,
                    self._admission_owner,
                    self._state_generation,
                    CircuitState.OPEN,
                    _force_open=True,
                )
            return CircuitAdmission(
                False,
                self._admission_owner,
                self._state_generation,
                self._state,
            )

    def record_success(self, admission: CircuitAdmission | None = None) -> None:
        """Record success, optionally limited to the admission that completed.

        Omitting ``admission`` preserves the original public API for existing
        callers. New asynchronous consumers should pass their ticket.
        """
        with self._lock:
            if admission is not None and not self._claim_admission(admission):
                return
            self._record_success_locked()

    def record_failure(self, admission: CircuitAdmission | None = None) -> None:
        """Record failure, optionally limited to the admission that completed.

        Omitting ``admission`` preserves the original public API for existing
        callers. New asynchronous consumers should pass their ticket.
        """
        with self._lock:
            if admission is not None and not self._claim_admission(admission):
                return
            self._record_failure_locked()

    def abandon_request(self, admission: CircuitAdmission) -> None:
        """Release an unfinished admission; a HALF_OPEN probe fails closed.

        Cancellation and unexpected exceptions still propagate from their
        consumers. Their ``finally`` blocks call this method so a probe cannot
        hold the HALF_OPEN gate forever. Abandoning an ordinary CLOSED request
        does not change the historical failure accounting.
        """
        with self._lock:
            if not self._claim_admission(admission):
                return
            if admission._state == CircuitState.HALF_OPEN:
                self._record_failure_locked()

    def _record_success_locked(self) -> None:
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            self._transition(self._state, CircuitState.CLOSED)
            self._failure_count = 0
            self._half_open_probe_sent = False  # RZ-33-11: reset probe gate
            self._current_recovery_timeout = self._base_recovery_timeout
        else:
            self._failure_count = 0

    def _record_failure_locked(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — reopen with doubled timeout
            self._half_open_probe_sent = False  # RZ-33-11: reset probe gate
            self._current_recovery_timeout = min(
                self._current_recovery_timeout * 2,
                self._max_recovery_timeout,
            )
            self._transition(self._state, CircuitState.OPEN)
        elif (
            self._state == CircuitState.CLOSED
            and self._failure_count >= self._failure_threshold
        ):
            self._transition(self._state, CircuitState.OPEN)

    def reset_for_testing(self) -> None:
        """Reset to initial state for unit tests."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._current_recovery_timeout = self._base_recovery_timeout
            self._half_open_probe_sent = False
            self._state_generation += 1
            self._active_half_open_admission = None
            circuit_state_gauge.set(CircuitState.CLOSED)

    # -- Internal ----------------------------------------------------------

    def _claim_admission(self, admission: CircuitAdmission) -> bool:
        """Consume a same-breaker ticket only while its issued state still holds."""
        if admission._owner is not self._admission_owner or admission._resolved:
            return False
        admission._resolved = True
        if not admission.allowed or admission._generation != self._state_generation:
            return False
        if admission._state == CircuitState.CLOSED:
            return self._state == CircuitState.CLOSED
        if admission._state == CircuitState.OPEN:
            return admission._force_open and self._state == CircuitState.OPEN
        return (
            admission._state == CircuitState.HALF_OPEN
            and self._state == CircuitState.HALF_OPEN
            and self._active_half_open_admission is admission
        )

    def _maybe_transition_to_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN if recovery timeout has elapsed.

        Must be called under self._lock.
        """
        if self._state != CircuitState.OPEN:
            return
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._current_recovery_timeout:
            self._transition(self._state, CircuitState.HALF_OPEN)

    def _transition(self, old_state: CircuitState, new_state: CircuitState) -> None:
        """Perform state transition with logging, metrics, and listener callbacks.

        Must be called under self._lock.
        """
        if old_state == new_state:
            return
        self._state = new_state
        self._state_generation += 1
        if old_state == CircuitState.HALF_OPEN or new_state != CircuitState.HALF_OPEN:
            self._active_half_open_admission = None
            self._half_open_probe_sent = False
        circuit_state_gauge.set(new_state)
        circuit_transitions_total.labels(
            from_state=old_state.name, to_state=new_state.name
        ).inc()
        _log.info(
            "rate_limit_circuit_breaker_transition",
            extra={
                "from_state": old_state.name,
                "to_state": new_state.name,
                "failure_count": self._failure_count,
                "recovery_timeout": self._current_recovery_timeout,
            },
        )

        listeners = list(self._state_listeners)
        for listener in listeners:
            try:
                res = listener(old_state, new_state)
                if inspect.isawaitable(res):
                    coro = typing.cast(
                        "typing.Coroutine[typing.Any, typing.Any, typing.Any]", res
                    )
                    try:
                        loop = asyncio.get_running_loop()
                        task: asyncio.Task[Any] = loop.create_task(coro)
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
                    except RuntimeError:
                        asyncio.run(coro)
            except Exception as exc:  # RZ-22-01-JUSTIFIED: Circuit breaker listener notification must not disrupt state transition
                _log.error(
                    "Error executing circuit breaker state listener: %s",
                    exc,
                    exc_info=True,
                )


# Module-level singleton — shared across all rate-limit checks in a worker.
# Uses functools.lru_cache for thread-safe lazy initialization (RZ-30-01 pattern).
@functools.lru_cache(maxsize=1)
def get_circuit_breaker() -> RedisCircuitBreaker:
    """Get or create the module-level circuit breaker singleton."""
    return RedisCircuitBreaker()
