"""Lifecycle contracts for a registered breaker shared across event loops."""

from __future__ import annotations

import asyncio
import threading

import pytest

import app.core.circuit_breaker as circuit_module
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from tests.helpers.async_events import wait_for_task_event
from tests.helpers.circuit_process import assert_circuit_scenario_completes


def test_contended_state_lock_wait_does_not_poll_with_timers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert_circuit_scenario_completes(
        _contended_state_lock_wait_does_not_poll_with_timers, with_monkeypatch=True
    )
    _contended_state_lock_wait_does_not_poll_with_timers(monkeypatch)


def _contended_state_lock_wait_does_not_poll_with_timers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    breaker = CircuitBreaker("non-polling-lock")
    assert breaker._lock.acquire()

    async def forbidden_sleep(*args: object, **kwargs: object) -> None:
        raise AssertionError("state-lock waits must be event-driven")

    async def verify_waiter() -> None:
        monkeypatch.setattr(asyncio, "sleep", forbidden_sleep)
        reset_task = asyncio.create_task(breaker.reset())
        marker = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(marker.set_result, None)
        try:
            await marker
            assert not reset_task.done()
            breaker._release_state_lock()
            await reset_task
        finally:
            if breaker._lock.locked():
                breaker._release_state_lock()
            if not reset_task.done():
                reset_task.cancel()
            await asyncio.gather(reset_task, return_exceptions=True)

    asyncio.run(verify_waiter())


def test_state_lock_wakes_queued_waiters_and_tolerates_cancel_during_wakeup() -> None:
    assert_circuit_scenario_completes(
        _state_lock_wakes_queued_waiters_and_tolerates_cancel_during_wakeup
    )
    _state_lock_wakes_queued_waiters_and_tolerates_cancel_during_wakeup()


def _state_lock_wakes_queued_waiters_and_tolerates_cancel_during_wakeup() -> None:
    breaker = CircuitBreaker("queued-lock-wakeup")
    assert breaker._lock.acquire()

    async def verify_waiters() -> None:
        acquired: list[int] = []

        async def use_lock(index: int) -> None:
            await breaker._acquire_state_lock()
            try:
                acquired.append(index)
            finally:
                breaker._release_state_lock()

        tasks = [asyncio.create_task(use_lock(index)) for index in range(20)]
        marker = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(marker.set_result, None)
        await marker
        assert len(breaker._state_waiters) == len(tasks)

        breaker._release_state_lock()
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        await asyncio.wait_for(asyncio.gather(*tasks[1:]), timeout=1)
        assert len(acquired) == len(tasks) - 1

    asyncio.run(verify_waiters())


def test_registered_breaker_lock_survives_contention_across_event_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert_circuit_scenario_completes(
        _registered_breaker_lock_survives_contention_across_event_loops,
        with_monkeypatch=True,
    )
    _registered_breaker_lock_survives_contention_across_event_loops(monkeypatch)


def _registered_breaker_lock_survives_contention_across_event_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(circuit_module, "_registry_lock", threading.Lock())
    monkeypatch.setattr(circuit_module, "_circuit_breakers", {})
    breaker = asyncio.run(circuit_module.get_circuit_breaker("shared-loop-breaker"))
    asyncio.run(breaker.force_open())
    breaker._internal_state.failure_count = 2

    lock_held = threading.Event()
    release_lock = threading.Event()

    def hold_lock_from_another_loop() -> None:
        async def hold() -> None:
            breaker._lock.acquire()
            lock_held.set()
            try:
                await asyncio.to_thread(release_lock.wait, 1)
            finally:
                breaker._release_state_lock()

        asyncio.run(hold())

    holder = threading.Thread(target=hold_lock_from_another_loop)
    holder.start()
    try:
        assert lock_held.wait(timeout=1)

        async def cancel_waiting_reset() -> None:
            reset_task = asyncio.create_task(breaker.reset())
            await asyncio.sleep(0.01)
            reset_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reset_task

        asyncio.run(cancel_waiting_reset())
        assert breaker.state.value == circuit_module.CircuitBreakerState.OPEN.value
        assert breaker.failure_count == 2
    finally:
        release_lock.set()
        holder.join(timeout=1)

    assert not holder.is_alive()

    asyncio.run(breaker.reset())
    assert breaker.state.value == circuit_module.CircuitBreakerState.CLOSED.value
    assert breaker.failure_count == 0


def test_closed_call_cannot_release_or_close_another_loops_half_open_probe() -> None:
    breaker = CircuitBreaker(
        "probe-permit-owner",
        config=CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=0,
            success_threshold=1,
        ),
    )
    closed_call_entered = threading.Event()
    release_closed_call = threading.Event()
    closed_call_finished = threading.Event()
    probe_entered = threading.Event()
    release_probe = threading.Event()
    background_errors: list[BaseException] = []

    def run_slow_closed_call() -> None:
        async def request() -> None:
            async with breaker:
                closed_call_entered.set()
                if not await asyncio.to_thread(release_closed_call.wait, 5):
                    raise AssertionError("closed call was not released")

        try:
            asyncio.run(request())
        except BaseException as exc:
            background_errors.append(exc)
        finally:
            closed_call_finished.set()

    background_loop_thread = threading.Thread(target=run_slow_closed_call)
    background_loop_thread.start()

    async def verify_probe_ownership() -> None:
        assert await asyncio.to_thread(closed_call_entered.wait, 5)
        with pytest.raises(RuntimeError, match="trip the circuit"):
            async with breaker:
                raise RuntimeError("trip the circuit")

        async def run_probe() -> None:
            async with breaker:
                probe_entered.set()
                if not await asyncio.to_thread(release_probe.wait, 5):
                    raise AssertionError("half-open probe was not released")

        probe_task = asyncio.create_task(run_probe())
        try:
            assert await asyncio.to_thread(probe_entered.wait, 5)
            release_closed_call.set()
            assert await asyncio.to_thread(closed_call_finished.wait, 5)
            assert breaker.state is circuit_module.CircuitBreakerState.HALF_OPEN
            assert breaker._internal_state.active_probe_count == 1

            with pytest.raises(CircuitBreakerOpenError):
                async with breaker:
                    pass
        finally:
            release_probe.set()
            await probe_task

    try:
        asyncio.run(verify_probe_ownership())
    finally:
        release_closed_call.set()
        release_probe.set()
        background_loop_thread.join(timeout=6)

    assert not background_loop_thread.is_alive()
    assert not background_errors


def test_force_open_preserves_in_flight_probe_reservation() -> None:
    breaker = CircuitBreaker(
        "force-open-probe-owner",
        config=CircuitBreakerConfig(
            recovery_timeout_seconds=0,
            success_threshold=10,
        ),
    )

    async def verify_probe_ownership() -> None:
        probe_entered = asyncio.Event()
        release_probe = asyncio.Event()
        await breaker.force_open()

        async def run_probe() -> None:
            async with breaker:
                probe_entered.set()
                await release_probe.wait()

        async with asyncio.TaskGroup() as tasks:
            probe_task = tasks.create_task(run_probe())
            try:
                await wait_for_task_event(probe_task, probe_entered)
                await breaker.force_open()

                with pytest.raises(CircuitBreakerOpenError):
                    async with breaker:
                        pass
            finally:
                release_probe.set()

    asyncio.run(verify_probe_ownership())


def test_cancelled_half_open_probe_releases_its_reservation() -> None:
    breaker = CircuitBreaker(
        "cancelled-probe-owner",
        config=CircuitBreakerConfig(
            recovery_timeout_seconds=0,
            success_threshold=10,
        ),
    )

    async def verify_cancellation() -> None:
        await breaker.force_open()
        entered = asyncio.Event()
        never_release = asyncio.Event()

        async def run_probe() -> None:
            async with breaker:
                entered.set()
                await never_release.wait()

        async with asyncio.TaskGroup() as tasks:
            task = tasks.create_task(run_probe())
            try:
                await wait_for_task_event(task, entered)
                assert breaker._internal_state.active_probe_count == 1
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                never_release.set()

        assert breaker._internal_state.active_probe_count == 0
        async with breaker:
            pass

    asyncio.run(verify_cancellation())


def test_repeated_cancel_during_probe_exit_does_not_leak_its_reservation() -> None:
    assert_circuit_scenario_completes(
        _repeated_cancel_during_probe_exit_does_not_leak_its_reservation
    )
    _repeated_cancel_during_probe_exit_does_not_leak_its_reservation()


def _repeated_cancel_during_probe_exit_does_not_leak_its_reservation() -> None:
    breaker = CircuitBreaker(
        "repeated-cancelled-probe-owner",
        config=CircuitBreakerConfig(
            recovery_timeout_seconds=0,
            success_threshold=10,
        ),
    )

    async def verify_cleanup() -> None:
        await breaker.force_open()
        entered = asyncio.Event()
        hold_body = asyncio.Event()

        async def run_probe() -> None:
            async with breaker:
                entered.set()
                await hold_body.wait()

        async with asyncio.TaskGroup() as tasks:
            probe_task = tasks.create_task(run_probe())
            lock_held = False
            try:
                await wait_for_task_event(probe_task, entered)
                await breaker._acquire_state_lock()
                lock_held = True
                probe_task.cancel()
                await asyncio.sleep(0)
                assert len(breaker._state_waiters) == 1

                probe_task.cancel()
                await asyncio.sleep(0)
                # Release before task drainage: __aexit__ must reacquire the
                # state lock to relinquish its permit before propagating cancel.
                breaker._release_state_lock()
                lock_held = False
                with pytest.raises(asyncio.CancelledError):
                    await probe_task
            finally:
                hold_body.set()
                if lock_held:
                    breaker._release_state_lock()

        assert breaker._internal_state.active_probe_count == 0
        assert not breaker._internal_state.active_probe_owners
        async with breaker:
            pass

    asyncio.run(verify_cleanup())
