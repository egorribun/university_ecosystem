"""Loop ownership tests for the asynchronous Web Push concurrency limiter."""

from __future__ import annotations

import asyncio
import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import webpush


def test_push_semaphore_is_scoped_to_its_event_loop(
    monkeypatch,
) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())

    async def contend_for_push_slots() -> asyncio.Semaphore:
        semaphore = webpush._get_push_semaphore()
        assert webpush._get_push_semaphore() is semaphore
        active = 0
        peak_active = 0
        enough_holders = asyncio.Event()
        release_holders = asyncio.Event()

        async def hold_slot() -> None:
            nonlocal active, peak_active
            async with semaphore:
                active += 1
                peak_active = max(peak_active, active)
                if active == webpush._PUSH_CONCURRENT_LIMIT:
                    enough_holders.set()
                await release_holders.wait()

        tasks = [
            asyncio.create_task(hold_slot())
            for _ in range(webpush._PUSH_CONCURRENT_LIMIT + 1)
        ]
        await asyncio.wait_for(enough_holders.wait(), timeout=1)
        await asyncio.sleep(0.05)
        assert active == webpush._PUSH_CONCURRENT_LIMIT
        assert peak_active == webpush._PUSH_CONCURRENT_LIMIT
        release_holders.set()
        await asyncio.gather(*tasks)
        return semaphore

    first_loop_semaphore = asyncio.run(contend_for_push_slots())
    second_loop_semaphore = asyncio.run(contend_for_push_slots())

    assert second_loop_semaphore is not first_loop_semaphore


def test_push_semaphore_cache_does_not_retain_closed_loop(monkeypatch) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())

    async def contend_for_push_slots() -> None:
        semaphore = webpush._get_push_semaphore()
        active = 0
        enough_holders = asyncio.Event()
        release_holders = asyncio.Event()

        async def hold_slot() -> None:
            nonlocal active
            async with semaphore:
                active += 1
                if active == webpush._PUSH_CONCURRENT_LIMIT:
                    enough_holders.set()
                await release_holders.wait()

        tasks = [
            asyncio.create_task(hold_slot())
            for _ in range(webpush._PUSH_CONCURRENT_LIMIT + 1)
        ]
        await asyncio.wait_for(enough_holders.wait(), timeout=1)
        await asyncio.sleep(0)
        release_holders.set()
        await asyncio.gather(*tasks)

    loop = asyncio.new_event_loop()
    loop_ref = weakref.ref(loop)
    loop.run_until_complete(asyncio.wait_for(contend_for_push_slots(), timeout=1))
    loop.close()
    del loop
    gc.collect()

    assert loop_ref() is None, "the semaphore cache must not retain a closed loop"


def test_push_send_concurrency_does_not_exceed_thirty(monkeypatch) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())
    worker_count = webpush._PUSH_CONCURRENT_LIMIT + 1
    active = 0
    peak_active = 0
    active_lock = Lock()
    limit_reached = Event()
    release_workers = Event()

    def blocking_send(subscription, _prepared):
        nonlocal active, peak_active
        with active_lock:
            active += 1
            peak_active = max(peak_active, active)
            if active >= webpush._PUSH_CONCURRENT_LIMIT:
                limit_reached.set()
        assert release_workers.wait(timeout=3)
        with active_lock:
            active -= 1
        return webpush.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
        )

    monkeypatch.setattr(webpush, "send_web_push", blocking_send)

    async def exercise_concurrency_limit() -> None:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(
            ThreadPoolExecutor(max_workers=webpush._PUSH_CONCURRENT_LIMIT + 2)
        )
        subscriptions = [
            SimpleNamespace(
                id=uuid4(),
                endpoint=f"https://push.example.test/{index}",
                user_id=uuid4(),
            )
            for index in range(worker_count)
        ]
        tasks = [
            asyncio.create_task(webpush._send_push_async(subscription, {}))
            for subscription in subscriptions
        ]
        try:
            reached_limit = await asyncio.wait_for(
                asyncio.to_thread(limit_reached.wait, 2), timeout=3
            )
            assert reached_limit
            await asyncio.sleep(0.05)
            with active_lock:
                assert active == webpush._PUSH_CONCURRENT_LIMIT
                assert peak_active == webpush._PUSH_CONCURRENT_LIMIT
        finally:
            release_workers.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(exercise_concurrency_limit())


def test_cancelled_waiting_push_does_not_consume_a_permit(monkeypatch) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())
    monkeypatch.setattr(webpush, "_PUSH_CONCURRENT_LIMIT", 1)
    first_worker_started = Event()
    release_first_worker = Event()
    send_calls = 0
    calls_lock = Lock()

    def blocking_send(subscription, _prepared):
        nonlocal send_calls
        with calls_lock:
            send_calls += 1
            call_number = send_calls
        if call_number == 1:
            first_worker_started.set()
            assert release_first_worker.wait(timeout=3)
        return webpush.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
        )

    monkeypatch.setattr(webpush, "send_web_push", blocking_send)

    async def exercise_waiter_cancellation() -> weakref.ReferenceType[
        asyncio.AbstractEventLoop
    ]:
        loop_ref = weakref.ref(asyncio.get_running_loop())
        subscriptions = [
            SimpleNamespace(
                id=uuid4(),
                endpoint=f"https://push.example.test/{index}",
                user_id=uuid4(),
            )
            for index in range(3)
        ]
        first = asyncio.create_task(webpush._send_push_async(subscriptions[0], {}))
        waiting = None
        replacement = None
        try:
            started = await asyncio.wait_for(
                asyncio.to_thread(first_worker_started.wait, 2), timeout=3
            )
            assert started

            waiting = asyncio.create_task(
                webpush._send_push_async(subscriptions[1], {})
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting

            replacement = asyncio.create_task(
                webpush._send_push_async(subscriptions[2], {})
            )
            await asyncio.sleep(0.05)
            assert send_calls == 1

            release_first_worker.set()
            first_result, replacement_result = await asyncio.wait_for(
                asyncio.gather(first, replacement), timeout=3
            )
            assert first_result.status == replacement_result.status == "sent"
            assert send_calls == 2
        finally:
            release_first_worker.set()
            tasks = [first]
            if waiting is not None:
                tasks.append(waiting)
            if replacement is not None:
                tasks.append(replacement)
            await asyncio.gather(*tasks, return_exceptions=True)
        return loop_ref

    loop_ref = asyncio.run(exercise_waiter_cancellation())
    gc.collect()
    assert loop_ref() is None


def test_cancelled_push_keeps_its_permit_until_worker_finishes(monkeypatch) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())
    monkeypatch.setattr(webpush, "_PUSH_CONCURRENT_LIMIT", 1)
    first_worker_started = Event()
    release_first_worker = Event()
    second_worker_started = Event()
    calls = 0
    calls_lock = Lock()

    def blocking_send(subscription, _prepared):
        nonlocal calls
        with calls_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_worker_started.set()
            assert release_first_worker.wait(timeout=3)
        else:
            second_worker_started.set()
        return webpush.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
        )

    monkeypatch.setattr(webpush, "send_web_push", blocking_send)

    async def exercise_cancellation() -> None:
        first_subscription = SimpleNamespace(
            id=uuid4(), endpoint="https://push.example.test/first", user_id=uuid4()
        )
        second_subscription = SimpleNamespace(
            id=uuid4(), endpoint="https://push.example.test/second", user_id=uuid4()
        )
        first = asyncio.create_task(webpush._send_push_async(first_subscription, {}))
        second = None
        try:
            started = await asyncio.wait_for(
                asyncio.to_thread(first_worker_started.wait, 2), timeout=3
            )
            assert started

            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            second = asyncio.create_task(
                webpush._send_push_async(second_subscription, {})
            )
            await asyncio.sleep(0.05)
            assert not second_worker_started.is_set()

            release_first_worker.set()
            result = await asyncio.wait_for(second, timeout=3)
            assert result.status == "sent"
            assert second_worker_started.is_set()
            assert calls == 2
        finally:
            release_first_worker.set()
            tasks = [first]
            if second is not None:
                tasks.append(second)
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(exercise_cancellation())


def test_timed_out_waiting_push_cancels_worker_and_releases_slot(
    monkeypatch,
) -> None:
    monkeypatch.setattr(webpush, "_push_semaphores", weakref.WeakKeyDictionary())
    monkeypatch.setattr(webpush, "_PUSH_CONCURRENT_LIMIT", 1)
    monkeypatch.setattr(webpush, "_PUSH_CALL_TIMEOUT_SECONDS", 3)
    first_worker_started = Event()
    release_first_worker = Event()
    calls = 0
    calls_lock = Lock()

    def blocking_send(subscription, _prepared):
        nonlocal calls
        with calls_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_worker_started.set()
            assert release_first_worker.wait(timeout=3)
        return webpush.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
        )

    monkeypatch.setattr(webpush, "send_web_push", blocking_send)

    async def exercise_timeout_while_waiting() -> None:
        subscriptions = [
            SimpleNamespace(
                id=uuid4(),
                endpoint=f"https://push.example.test/{label}",
                user_id=uuid4(),
            )
            for label in ("first", "waiting", "replacement")
        ]
        first = asyncio.create_task(webpush._send_push_async(subscriptions[0], {}))
        try:
            started = await asyncio.wait_for(
                asyncio.to_thread(first_worker_started.wait, 2), timeout=3
            )
            assert started

            monkeypatch.setattr(webpush, "_PUSH_CALL_TIMEOUT_SECONDS", 0.02)
            timed_out = await webpush._send_push_async(subscriptions[1], {})
            assert timed_out.status == "error"
            assert timed_out.error == "push delivery timed out"
            assert calls == 1

            release_first_worker.set()
            first_result = await asyncio.wait_for(first, timeout=3)
            monkeypatch.setattr(webpush, "_PUSH_CALL_TIMEOUT_SECONDS", 3)
            replacement = await asyncio.wait_for(
                webpush._send_push_async(subscriptions[2], {}), timeout=3
            )

            assert first_result.status == replacement.status == "sent"
            assert calls == 2
        finally:
            release_first_worker.set()
            await asyncio.gather(first, return_exceptions=True)

    asyncio.run(exercise_timeout_while_waiting())
