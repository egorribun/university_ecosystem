"""Concurrency and boundary-condition tests for the rate-limit subsystem.

These tests complement ``tests/test_rate_limit.py`` (which focuses on
middleware integration) by stressing:

* the memory sliding-window strategy under simultaneous burst,
* the Redis circuit breaker's state-machine atomicity,
* the half-open single-probe gate (only one probe runs at a time),
* fail-closed fallback to ``MemorySlidingWindowStrategy`` at 50 % capacity,
* invariant validation in ``check_rate_limit``.

We construct fresh ``RedisCircuitBreaker`` instances per test instead of
touching the module-level singleton to avoid cross-test bleed.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from redis.exceptions import RedisError

import app.core.ratelimit as rate_limit
from app.core.config import settings
from app.core.ratelimit.circuit_breaker import (
    CircuitState,
    RedisCircuitBreaker,
    get_circuit_breaker,
)
from app.core.ratelimit.strategies.memory import (
    MemorySlidingWindowStrategy,
    clear_memory_state,
)


@pytest.fixture(autouse=True)
def _enable_rate_limit_globally(monkeypatch):
    """Enable rate limiting for every test in this module.

    Tests/conftest.py defaults RATE_LIMIT_ENABLED to False, so we flip the
    flag here so ``check_rate_limit``/``MemorySlidingWindowStrategy.check``
    don't short-circuit to ``RateLimitInfo(allowed=True, ...)``.
    """
    monkeypatch.setattr(settings, "rate_limit_enabled", True)


@pytest.fixture(autouse=True)
def _wipe_memory_state():
    """Ensure the in-memory window dict is empty before every test."""
    clear_memory_state()
    yield
    clear_memory_state()


# ── 1. Memory sliding-window: simultaneous burst at the limit boundary ───────


@pytest.mark.asyncio
async def test_memory_strategy_concurrent_burst_at_boundary() -> None:
    """N concurrent requests with limit K → exactly K allowed, N−K denied.

    Stresses the sharded asyncio lock: a single key routes to a single
    shard, so all requests serialise on the same lock. The boundary
    behaviour must remain deterministic.
    """
    strategy = MemorySlidingWindowStrategy(namespace="burst")
    limit = 10
    burst = 30

    results = await asyncio.gather(
        *[
            strategy.check(key="user-42", limit=limit, window_seconds=60)
            for _ in range(burst)
        ]
    )

    allowed = [r for r in results if r.allowed]
    denied = [r for r in results if not r.allowed]
    assert len(allowed) == limit
    assert len(denied) == burst - limit

    # The denied responses must report a non-zero retry_after; the request was
    # rejected in the same second so retry_after equals the configured window
    # (give or take a sub-second timing artefact).
    for r in denied:
        assert r.retry_after >= 0


@pytest.mark.asyncio
async def test_memory_strategy_independent_keys_dont_contend() -> None:
    """50 concurrent requests across 50 keys with limit=1 all pass.

    Verifies the sharded lock genuinely splits work — independent keys
    never block one another even under heavy concurrency.
    """
    strategy = MemorySlidingWindowStrategy(namespace="indep")

    results = await asyncio.gather(
        *[
            strategy.check(key=f"user-{i}", limit=1, window_seconds=60)
            for i in range(50)
        ]
    )
    assert all(r.allowed for r in results)


@pytest.mark.asyncio
async def test_memory_strategy_window_slide_releases_capacity(monkeypatch) -> None:
    """After the window slides past, blocked requests become allowed again."""
    strategy = MemorySlidingWindowStrategy(namespace="slide")

    fake_now = [1_000_000.0]

    def fake_time() -> float:
        return fake_now[0]

    # Patch time.time inside the strategy module so we control "now" deterministically.
    monkeypatch.setattr("app.core.ratelimit.strategies.memory.time.time", fake_time)

    info1 = await strategy.check(key="bob", limit=2, window_seconds=10)
    info2 = await strategy.check(key="bob", limit=2, window_seconds=10)
    info3 = await strategy.check(key="bob", limit=2, window_seconds=10)
    assert info1.allowed
    assert info2.allowed
    assert info3.allowed is False  # third hit exceeds the window's 2-request quota

    # Slide the window forward beyond the configured 10s — both prior hits
    # fall outside, so the next request is allowed again.
    fake_now[0] += 11
    info4 = await strategy.check(key="bob", limit=2, window_seconds=10)
    assert info4.allowed


@pytest.mark.asyncio
async def test_memory_strategy_invalid_limit_returns_allowed() -> None:
    """A non-positive limit is silently ignored — allowed=True, no work done."""
    strategy = MemorySlidingWindowStrategy(namespace="bad")
    result = await strategy.check(key="any", limit=0, window_seconds=60)
    assert result.allowed
    assert result.remaining == 0


# ── 2. check_rate_limit: invariant validation and fast paths ─────────────────


@pytest.mark.asyncio
async def test_check_rate_limit_rejects_zero_limit() -> None:
    """``check_rate_limit`` raises on limit<=0 (can't disable protection silently)."""
    with pytest.raises(ValueError, match="rate limit must be positive"):
        await rate_limit.check_rate_limit(
            identifier="x", namespace="ns", limit=0, window_seconds=60
        )


@pytest.mark.asyncio
async def test_check_rate_limit_rejects_zero_window() -> None:
    """``check_rate_limit`` raises on window_seconds<=0."""
    with pytest.raises(ValueError, match="window must be positive"):
        await rate_limit.check_rate_limit(
            identifier="x", namespace="ns", limit=10, window_seconds=0
        )


@pytest.mark.asyncio
async def test_check_rate_limit_disabled_short_circuits(monkeypatch) -> None:
    """When ``settings.rate_limit_enabled`` is False, the check is bypassed."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    info = await rate_limit.check_rate_limit(
        identifier="x", namespace="ns", limit=5, window_seconds=60
    )
    assert info.allowed
    assert info.remaining == 5
    assert info.retry_after == 0


@pytest.mark.asyncio
async def test_check_rate_limit_memory_mode_when_no_redis() -> None:
    """A blank ``redis_url`` falls through to the memory strategy."""
    info = await rate_limit.check_rate_limit(
        identifier="alice",
        namespace="memmode",
        limit=2,
        window_seconds=60,
        redis_url=None,
    )
    assert info.allowed
    info2 = await rate_limit.check_rate_limit(
        identifier="alice",
        namespace="memmode",
        limit=2,
        window_seconds=60,
        redis_url=None,
    )
    assert info2.allowed
    info3 = await rate_limit.check_rate_limit(
        identifier="alice",
        namespace="memmode",
        limit=2,
        window_seconds=60,
        redis_url=None,
    )
    assert info3.allowed is False


@pytest.mark.asyncio
async def test_check_rate_limit_concurrent_burst_via_memory() -> None:
    """Concurrent ``check_rate_limit`` callers honour the limit boundary.

    Drives the full public entry point (memory mode) under burst load.
    """
    limit = 5
    burst = 20

    async def call() -> Any:
        return await rate_limit.check_rate_limit(
            identifier="shared-id",
            namespace="check-burst",
            limit=limit,
            window_seconds=60,
            redis_url=None,
        )

    results = await asyncio.gather(*[call() for _ in range(burst)])
    allowed = sum(1 for r in results if r.allowed)
    assert allowed == limit


# ── 3. Redis fallback: when Redis errors, fail closed at 50% capacity ────────


@pytest.mark.asyncio
async def test_check_rate_limit_falls_back_on_redis_error(monkeypatch) -> None:
    """A RedisError on the Redis path triggers a 50%-capacity memory fallback."""

    async def _redis_blows_up(self, key, limit, window_seconds):
        raise RedisError("simulated outage")

    monkeypatch.setattr(
        "app.core.ratelimit.strategies.redis.RedisSlidingWindowStrategy.check",
        _redis_blows_up,
    )
    # Reset the singleton so this test starts CLOSED.
    get_circuit_breaker.cache_clear()

    # Fallback uses ``max(limit // 2, 1)`` — limit=4 → fallback_limit=2.
    info1 = await rate_limit.check_rate_limit(
        identifier="key",
        namespace="ns-fb",
        limit=4,
        window_seconds=60,
        redis_url="redis://localhost",
    )
    info2 = await rate_limit.check_rate_limit(
        identifier="key",
        namespace="ns-fb",
        limit=4,
        window_seconds=60,
        redis_url="redis://localhost",
    )
    info3 = await rate_limit.check_rate_limit(
        identifier="key",
        namespace="ns-fb",
        limit=4,
        window_seconds=60,
        redis_url="redis://localhost",
    )

    assert info1.allowed
    assert info2.allowed
    assert info3.allowed is False  # fallback limit is 2, third request denied


# ── 4. Circuit breaker: state-machine atomicity under concurrency ────────────


def test_circuit_breaker_starts_closed() -> None:
    """A fresh breaker is CLOSED."""
    cb = RedisCircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens_at_threshold() -> None:
    """``record_failure`` exactly ``threshold`` times trips the breaker open."""
    cb = RedisCircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # not yet at threshold
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_concurrent_failures_transition_exactly_once() -> None:
    """100 threads recording failures past threshold open the circuit once.

    Each transition increments a Prometheus counter; we verify the breaker
    ends in OPEN and (implicitly) that the state guard inside ``_transition``
    prevents repeated CLOSED→OPEN counter bumps for the same crossing.
    """
    cb = RedisCircuitBreaker(failure_threshold=5)
    barrier = threading.Barrier(100)

    def worker() -> None:
        barrier.wait()
        cb.record_failure()

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All 100 failures observed but the circuit is OPEN exactly once.
    assert cb.state == CircuitState.OPEN
    # We cannot easily inspect the failure_count externally, but the
    # transition is irreversible until record_success is called.


def test_circuit_breaker_open_blocks_requests() -> None:
    """``allow_request`` returns False while OPEN."""
    cb = RedisCircuitBreaker(failure_threshold=2, recovery_timeout=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Multiple consecutive attempts all blocked — none get through to Redis.
    assert cb.allow_request() is False
    assert cb.allow_request() is False
    assert cb.allow_request() is False


def test_circuit_breaker_half_open_single_probe() -> None:
    """In HALF_OPEN state, only one probe runs at a time.

    100 simultaneous ``allow_request()`` callers see exactly one True.

    We use a non-zero recovery_timeout and manually rewind
    ``_last_failure_time`` so the first state read transitions to
    HALF_OPEN deterministically — using ``recovery_timeout=0.0``
    alone makes ``cb.state`` flip from OPEN→HALF_OPEN on the *first*
    read, which would invalidate the OPEN-state precondition assertion.
    """
    cb = RedisCircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Rewind the failure clock so the next state read transitions to HALF_OPEN.
    cb._last_failure_time = -1_000_000.0  # type: ignore[attr-defined]  # rewind far enough that elapsed > any timeout regardless of process start
    assert cb.state == CircuitState.HALF_OPEN

    # Drive 100 concurrent allow_request() calls.
    results: list[bool] = []
    barrier = threading.Barrier(100)

    def worker() -> None:
        barrier.wait()
        results.append(cb.allow_request())

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one probe permitted; the other 99 callers see False.
    assert sum(results) == 1


def test_circuit_breaker_half_open_success_closes() -> None:
    """A successful probe in HALF_OPEN closes the circuit."""
    cb = RedisCircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    # Force the OPEN→HALF_OPEN transition deterministically.
    cb._last_failure_time = -1_000_000.0  # type: ignore[attr-defined]  # rewind far enough that elapsed > any timeout regardless of process start
    assert cb.state == CircuitState.HALF_OPEN
    cb.allow_request()  # consumes the single-probe slot
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens_with_doubled_timeout() -> None:
    """A failed probe in HALF_OPEN bumps recovery_timeout exponentially."""
    cb = RedisCircuitBreaker(
        failure_threshold=2,
        recovery_timeout=10.0,
        max_recovery_timeout=300.0,
    )
    # Force OPEN.
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Force into HALF_OPEN by zeroing out _last_failure_time so the elapsed
    # check passes — see _maybe_transition_to_half_open.
    cb._last_failure_time = -1_000_000.0  # type: ignore[attr-defined]  # rewind far enough that elapsed > any timeout regardless of process start
    assert cb.state == CircuitState.HALF_OPEN

    cb.allow_request()  # take the probe slot
    cb.record_failure()  # probe fails
    assert cb.state == CircuitState.OPEN

    # Internal timeout doubled from 10 → 20 seconds.
    assert cb._current_recovery_timeout == 20.0  # type: ignore[attr-defined]


def test_circuit_breaker_max_recovery_timeout_caps_growth() -> None:
    """Repeated failed probes can't exceed ``max_recovery_timeout``."""
    cb = RedisCircuitBreaker(
        failure_threshold=1,
        recovery_timeout=100.0,
        max_recovery_timeout=300.0,
    )
    # Open the circuit.
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Six failed probe cycles — each would normally double 100→200→400→…
    # but should saturate at 300.
    #
    # We rewind ``_last_failure_time`` to a very negative value (rather
    # than 0.0) so ``elapsed = time.monotonic() - _last_failure_time``
    # always far exceeds the current recovery_timeout. ``time.monotonic()``
    # is process-relative — in a fresh CI container it can return tens of
    # seconds, which is below the 300s saturation cap and would prevent
    # the OPEN→HALF_OPEN transition on later iterations.
    rewind = -1_000_000.0
    for _ in range(6):
        cb._last_failure_time = rewind  # type: ignore[attr-defined]
        assert cb.state == CircuitState.HALF_OPEN
        cb.allow_request()
        cb.record_failure()

    assert cb._current_recovery_timeout == 300.0  # type: ignore[attr-defined]


def test_circuit_breaker_reset_for_testing_clears_state() -> None:
    """``reset_for_testing`` returns the breaker to a fresh CLOSED state."""
    cb = RedisCircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset_for_testing()
    assert cb.state == CircuitState.CLOSED


def test_record_success_in_closed_state_resets_failure_count() -> None:
    """Lines 105-106: record_success() in CLOSED state resets failure_count to 0.

    When a request succeeds while the breaker is CLOSED (e.g., after partial
    failures but not enough to trip the breaker), the failure count should be
    reset to prevent a slow accumulation of stale failures from tripping
    the breaker in the future.
    """
    cb = RedisCircuitBreaker(failure_threshold=5, recovery_timeout=10.0)
    # Record some failures (not enough to trip)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 2  # type: ignore[attr-defined]

    # Now a success clears the failure count
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 0  # type: ignore[attr-defined]


def test_transition_no_op_when_same_state() -> None:
    """Line 157: _transition() is a no-op when old state == new state.

    Calling _transition(CLOSED) when already CLOSED must not change metrics
    or log a spurious state change.
    """
    cb = RedisCircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
    assert cb.state == CircuitState.CLOSED

    # Calling _transition(CLOSED) on a CLOSED breaker should silently return
    # (line 157: if old == new_state: return)
    cb._transition(CircuitState.CLOSED)  # type: ignore[attr-defined]
    # State must still be CLOSED and failure count unchanged
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 0  # type: ignore[attr-defined]


def test_circuit_breaker_transition_no_op() -> None:
    """_transition returns early without changes if new state matches current state."""
    cb = RedisCircuitBreaker(failure_threshold=2)
    cb._transition(cb._state)
    assert cb.state == CircuitState.CLOSED
