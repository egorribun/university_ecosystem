"""Shutdown and task-context edges for the cross-loop state lock."""

from __future__ import annotations

import asyncio

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerState


def test_state_lock_release_skips_waiter_from_closed_loop() -> None:
    breaker = CircuitBreaker("closed-loop-waiter")
    stale_loop = asyncio.new_event_loop()
    waiter = stale_loop.create_future()
    stale_loop.close()
    breaker._state_waiters.append((stale_loop, waiter))
    assert breaker._lock.acquire()

    breaker._release_state_lock()

    assert not breaker._lock.locked()
    assert breaker._state_waiters == []
    assert not waiter.done()


def test_half_open_entry_without_current_task_releases_state_lock() -> None:
    breaker = CircuitBreaker("half-open-callback-entry")
    breaker._internal_state.state = CircuitBreakerState.HALF_OPEN

    async def enter_from_callback() -> None:
        loop = asyncio.get_running_loop()
        completed = loop.create_future()

        def invoke_without_task() -> None:
            coroutine = breaker.__aenter__()
            try:
                coroutine.send(None)
            except RuntimeError as error:
                completed.set_result(str(error))
            except BaseException as error:
                completed.set_exception(error)
            else:
                completed.set_exception(
                    AssertionError("HALF_OPEN entry unexpectedly succeeded")
                )

        loop.call_soon(invoke_without_task)
        error = await asyncio.wait_for(completed, timeout=1)

        assert error == "circuit breaker probe requires an asyncio task"
        assert breaker.state is CircuitBreakerState.HALF_OPEN
        assert breaker._internal_state.active_probe_count == 0
        assert not breaker._lock.locked()

    asyncio.run(enter_from_callback())
