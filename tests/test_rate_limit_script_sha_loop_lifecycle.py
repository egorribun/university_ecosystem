"""Loop-lifecycle coverage for the Redis Lua script SHA cache."""

from __future__ import annotations

import asyncio
import gc
import threading
import weakref
from types import SimpleNamespace
from weakref import WeakKeyDictionary

import pytest

from app.core.ratelimit.strategies import redis as redis_strategy


@pytest.fixture
def isolated_sha_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_strategy, "_RATE_LIMIT_SHA", None)
    if hasattr(redis_strategy, "_SHA_LOCKS"):
        monkeypatch.setattr(redis_strategy, "_SHA_LOCKS", WeakKeyDictionary())
    if hasattr(redis_strategy, "_SHA_LOCK"):
        monkeypatch.setattr(redis_strategy, "_SHA_LOCK", asyncio.Lock())


async def _load_with_same_loop_contention() -> weakref.ReferenceType[
    asyncio.AbstractEventLoop
]:
    started = asyncio.Event()
    release = asyncio.Event()

    async def script_load(_script: str) -> str:
        started.set()
        await release.wait()
        return "synthetic-script-sha"

    client = SimpleNamespace(script_load=script_load)
    first = asyncio.create_task(redis_strategy._load_script_sha(client))
    await started.wait()
    second = asyncio.create_task(redis_strategy._load_script_sha(client))
    await asyncio.sleep(0)
    release.set()
    assert await asyncio.gather(first, second) == [
        "synthetic-script-sha",
        "synthetic-script-sha",
    ]
    return weakref.ref(asyncio.get_running_loop())


def test_script_sha_reload_uses_lock_for_current_event_loop(
    isolated_sha_state: None,
) -> None:
    first_loop_ref = asyncio.run(_load_with_same_loop_contention())
    redis_strategy._RATE_LIMIT_SHA = None

    second_loop_ref = asyncio.run(_load_with_same_loop_contention())
    gc.collect()

    assert first_loop_ref() is None
    assert second_loop_ref() is None


def test_script_sha_lock_does_not_keep_closed_loop_alive(
    isolated_sha_state: None,
) -> None:
    loop_ref = asyncio.run(_load_with_same_loop_contention())
    gc.collect()

    assert loop_ref() is None


@pytest.mark.asyncio
async def test_cancelled_script_load_releases_loop_lock(
    isolated_sha_state: None,
) -> None:
    started = asyncio.Event()
    never_release = asyncio.Event()

    async def blocked_script_load(_script: str) -> str:
        started.set()
        await never_release.wait()
        return "unreachable-sha"

    blocked_client = SimpleNamespace(script_load=blocked_script_load)
    loading = asyncio.create_task(redis_strategy._load_script_sha(blocked_client))
    await started.wait()
    loading.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loading

    async def recovered_script_load(_script: str) -> str:
        return "recovered-sha"

    recovered_client = SimpleNamespace(script_load=recovered_script_load)
    assert await redis_strategy._load_script_sha(recovered_client) == "recovered-sha"


def test_script_sha_cache_handles_concurrent_event_loops(
    isolated_sha_state: None,
) -> None:
    """Concurrent loops use independent locks and release their loop entries."""
    load_barrier = threading.Barrier(2)
    lock_ids: dict[str, int] = {}
    results: dict[
        str, tuple[str, weakref.ReferenceType[asyncio.AbstractEventLoop]]
    ] = {}
    errors: list[BaseException] = []

    def make_client(name: str) -> SimpleNamespace:
        async def script_load(_script: str) -> str:
            lock_ids[name] = id(redis_strategy._get_sha_lock())
            await asyncio.to_thread(load_barrier.wait, timeout=2)
            return "concurrent-synthetic-sha"

        return SimpleNamespace(script_load=script_load)

    clients = {"first": make_client("first"), "second": make_client("second")}

    def load_in_own_loop(name: str) -> None:
        async def load() -> tuple[
            str, weakref.ReferenceType[asyncio.AbstractEventLoop]
        ]:
            loop = asyncio.get_running_loop()
            result = await redis_strategy._load_script_sha(clients[name])
            return result, weakref.ref(loop)

        try:
            results[name] = asyncio.run(load())
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=load_in_own_loop, args=(name,))
        for name in ("first", "second")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=4)
    gc.collect()

    assert all(not thread.is_alive() for thread in threads)
    assert not errors
    assert set(results) == {"first", "second"}
    assert {result for result, _loop_ref in results.values()} == {
        "concurrent-synthetic-sha"
    }
    assert len(set(lock_ids.values())) == 2
    assert all(loop_ref() is None for _result, loop_ref in results.values())
    assert len(redis_strategy._SHA_LOCKS) == 0
