"""Regression tests for process-wide in-memory rate-limit synchronization."""

from __future__ import annotations

import asyncio
import gc
import threading
import time
import weakref
from _thread import LockType
from collections import deque

import pytest

from app.core.ratelimit import cleanup
from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies import memory
from app.core.ratelimit.utils import compose_identifier


def test_memory_rate_limit_lock_survives_sequential_event_loops() -> None:
    """A contended shard lock can be reused after its original loop closes."""
    namespace = "loop-lifecycle-regression"
    key = "same-shard-key"
    strategy = memory.MemorySlidingWindowStrategy(namespace=namespace)
    lock_key = compose_identifier(namespace, key)
    memory._memory_windows.pop(lock_key, None)
    remaining_values: list[int] = []

    async def make_contended_request() -> weakref.ReferenceType[
        asyncio.AbstractEventLoop
    ]:
        lock = memory._shard_lock(lock_key)
        if isinstance(lock, asyncio.Lock):
            await lock.acquire()
            waiter = asyncio.create_task(lock.acquire())
            await asyncio.sleep(0)
            lock.release()
            await waiter
            lock.release()
        else:
            await asyncio.to_thread(lock.acquire)
            waiter_started = asyncio.Event()

            async def wait_for_thread_lock() -> None:
                waiter_started.set()
                await asyncio.to_thread(lock.acquire)

            waiter = asyncio.create_task(wait_for_thread_lock())
            await waiter_started.wait()
            await asyncio.sleep(0)
            lock.release()
            await waiter
            lock.release()

        result = await strategy.check(key, limit=5, window_seconds=60)
        assert result.allowed
        remaining_values.append(result.remaining)
        return weakref.ref(asyncio.get_running_loop())

    first_loop_ref = asyncio.run(make_contended_request())
    second_loop_ref = asyncio.run(make_contended_request())
    memory._memory_windows.pop(lock_key, None)
    gc.collect()

    assert remaining_values == [4, 3]
    assert first_loop_ref() is None
    assert second_loop_ref() is None


def test_memory_rate_limit_stays_atomic_across_event_loop_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate loops cannot both admit the last slot in one shared window."""
    namespace = "cross-thread-loop-regression"
    key = "single-slot-key"
    lock_key = compose_identifier(namespace, key)
    strategy = memory.MemorySlidingWindowStrategy(namespace=namespace)
    first_checking = threading.Event()
    second_attempting_lock = threading.Event()

    class CoordinatedWindow(deque[float]):
        def __init__(self) -> None:
            super().__init__()
            self._wait_for_second = True

        def __bool__(self) -> bool:
            return deque.__len__(self) > 0

        def __len__(self) -> int:
            length = deque.__len__(self)
            if (
                threading.current_thread().name == "rate-limit-first"
                and self._wait_for_second
            ):
                self._wait_for_second = False
                first_checking.set()
                if not second_attempting_lock.wait(timeout=2):
                    raise AssertionError("second loop did not contend for the shard")
            return length

    class ObservedThreadLock:
        def __init__(self, lock: LockType) -> None:
            self._lock = lock

        def __enter__(self) -> ObservedThreadLock:
            if threading.current_thread().name == "rate-limit-second":
                second_attempting_lock.set()
            self._lock.acquire()
            return self

        def __exit__(self, *_exc: object) -> None:
            self._lock.release()

    window = CoordinatedWindow()
    memory._memory_windows[lock_key] = window
    shard_lock = memory._shard_lock(lock_key)
    assert isinstance(shard_lock, LockType)
    monkeypatch.setattr(
        memory, "_shard_lock", lambda _key: ObservedThreadLock(shard_lock)
    )
    results: dict[str, RateLimitInfo] = {}
    errors: list[BaseException] = []

    def make_request(name: str) -> None:
        try:
            results[name] = asyncio.run(strategy.check(key, limit=1, window_seconds=60))
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(
        target=make_request, args=("first",), name="rate-limit-first"
    )
    second = threading.Thread(
        target=make_request, args=("second",), name="rate-limit-second"
    )
    try:
        first.start()
        assert first_checking.wait(timeout=2)
        second.start()
    finally:
        second_attempting_lock.set()
        first.join(timeout=2)
        if second.ident is not None:
            second.join(timeout=2)
        memory._memory_windows.pop(lock_key, None)

    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors
    assert set(results) == {"first", "second"}
    assert sum(bool(result.allowed) for result in results.values()) == 1
    assert len(window) == 1


def test_cleanup_key_snapshot_survives_cross_thread_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup must snapshot keys safely while another loop inserts a key."""
    snapshot_paused = threading.Event()
    writer_attempted = threading.Event()
    iteration_errors: list[str] = []

    class InterleavingWindows(dict[str, deque[float]]):
        def __init__(self) -> None:
            super().__init__({"existing-one": deque(), "existing-two": deque()})
            self.pause_next_snapshot = True

        def keys(self):  # type: ignore[no-untyped-def]
            keys_view = dict.keys(self)
            owner = self

            class PausingView:
                def __iter__(self):  # type: ignore[no-untyped-def]
                    iterator = iter(keys_view)
                    try:
                        first = next(iterator)
                    except StopIteration:
                        return
                    yield first
                    if owner.pause_next_snapshot:
                        owner.pause_next_snapshot = False
                        snapshot_paused.set()
                        if not writer_attempted.wait(timeout=2):
                            raise AssertionError("writer did not reach the snapshot")
                        time.sleep(0.05)
                    try:
                        yield from iterator
                    except RuntimeError as exc:
                        iteration_errors.append(str(exc))
                        raise

            return PausingView()

    windows = InterleavingWindows()
    monkeypatch.setattr(memory, "_memory_windows", windows)
    monkeypatch.setattr(cleanup, "_memory_windows", windows)
    strategy = memory.MemorySlidingWindowStrategy(namespace="cleanup-cross-loop")
    loop = asyncio.new_event_loop()
    task_holder: list[asyncio.Task[None]] = []
    writer_errors: list[BaseException] = []

    def insert_from_another_loop() -> None:
        if not snapshot_paused.wait(timeout=2):
            writer_errors.append(AssertionError("cleanup did not begin its snapshot"))
            return
        writer_attempted.set()
        try:
            asyncio.run(strategy.check("new-key", limit=5, window_seconds=60))
        except BaseException as exc:
            writer_errors.append(exc)
        finally:
            loop.call_soon_threadsafe(task_holder[0].cancel)

    writer = threading.Thread(target=insert_from_another_loop, name="rate-limit-writer")
    writer.start()

    async def run_cleanup() -> None:
        task_holder.append(asyncio.create_task(cleanup._memory_cleanup_loop(0)))
        await task_holder[0]

    try:
        loop.run_until_complete(run_cleanup())
        writer.join(timeout=3)
    finally:
        if writer.is_alive():
            writer.join(timeout=3)
        loop.close()

    assert not writer.is_alive()
    assert not writer_errors
    assert not iteration_errors


def test_cleanup_task_restarts_after_graceful_loop_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup task can be recreated after asyncio.run cancels its loop."""
    monkeypatch.setattr(cleanup, "_cleanup_task", None)

    async def start_cleanup() -> asyncio.Task[None]:
        cleanup.start_memory_cleanup_task(interval_seconds=3600)
        task = cleanup._cleanup_task
        assert task is not None
        await asyncio.sleep(0)
        return task

    first_task = asyncio.run(start_cleanup())
    assert first_task.done()

    async def restart_and_stop_cleanup() -> None:
        cleanup.start_memory_cleanup_task(interval_seconds=3600)
        second_task = cleanup._cleanup_task
        assert second_task is not None
        assert second_task is not first_task
        await cleanup.stop_memory_cleanup_task()

    asyncio.run(restart_and_stop_cleanup())
    assert cleanup._cleanup_task is None
