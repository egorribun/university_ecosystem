"""PERF-30-01: Circuit breaker for Redis-backed rate limiting.

Three-state machine preventing cascading failures when Redis is unresponsive:
  CLOSED    → normal operation, forward to Redis
  OPEN      → skip Redis, return fallback immediately
  HALF_OPEN → allow one probe request; success→CLOSED, fail→OPEN (doubled timeout)

Thread-safe under Python 3.13+ free-threading via threading.Lock.
"""

from __future__ import annotations

import enum
import functools
import logging
import threading
import time

from prometheus_client import Counter, Gauge

_log = logging.getLogger(__name__)

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
        self._lock = threading.Lock()

        circuit_state_gauge.set(CircuitState.CLOSED)

    # -- Public API --------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def allow_request(self) -> bool:
        """Return True if the request should attempt Redis."""
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                # RZ-33-11: Allow only one probe — subsequent callers wait for
                # the probe result instead of all proceeding simultaneously.
                if not self._half_open_probe_sent:
                    self._half_open_probe_sent = True
                    return True  # single probe request
                return False  # another probe already in-flight
            return False  # OPEN → use fallback

    def record_success(self) -> None:
        """Record a successful Redis operation."""
        with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                self._transition(CircuitState.CLOSED)
                self._failure_count = 0
                self._half_open_probe_sent = False  # RZ-33-11: reset probe gate
                self._current_recovery_timeout = self._base_recovery_timeout
            else:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed Redis operation."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen with doubled timeout
                self._half_open_probe_sent = False  # RZ-33-11: reset probe gate
                self._current_recovery_timeout = min(
                    self._current_recovery_timeout * 2,
                    self._max_recovery_timeout,
                )
                self._transition(CircuitState.OPEN)
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                self._transition(CircuitState.OPEN)

    def reset_for_testing(self) -> None:
        """Reset to initial state for unit tests."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._current_recovery_timeout = self._base_recovery_timeout
            circuit_state_gauge.set(CircuitState.CLOSED)

    # -- Internal ----------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN if recovery timeout has elapsed.

        Must be called under self._lock.
        """
        if self._state != CircuitState.OPEN:
            return
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._current_recovery_timeout:
            self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """Perform state transition with logging and metrics.

        Must be called under self._lock.
        """
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        circuit_state_gauge.set(new_state)
        circuit_transitions_total.labels(
            from_state=old.name, to_state=new_state.name
        ).inc()
        _log.info(
            "rate_limit_circuit_breaker_transition",
            extra={
                "from_state": old.name,
                "to_state": new_state.name,
                "failure_count": self._failure_count,
                "recovery_timeout": self._current_recovery_timeout,
            },
        )


# Module-level singleton — shared across all rate-limit checks in a worker.
# Uses functools.lru_cache for thread-safe lazy initialization (RZ-30-01 pattern).
@functools.lru_cache(maxsize=1)
def get_circuit_breaker() -> RedisCircuitBreaker:
    """Get or create the module-level circuit breaker singleton."""
    return RedisCircuitBreaker()
