"""Closure tests for the lock double-check paths in request coalescing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.utils import request_coalescing as module


@pytest.mark.asyncio
async def test_decorator_rechecks_in_flight_after_waiting_for_existing_lock():
    module._in_flight_requests.clear()
    module._request_locks.clear()
    calls = 0

    @module.coalesce_requests(prefix="lock-race")
    async def load(value: str) -> str:
        nonlocal calls
        calls += 1
        return value

    key = module._build_request_key("lock-race", "value")
    lock = asyncio.Lock()
    await lock.acquire()
    module._request_locks[key] = lock
    task = asyncio.create_task(load("value"))
    await asyncio.sleep(0)
    future = asyncio.get_running_loop().create_future()
    module._in_flight_requests[key] = future
    future.set_result("shared")
    lock.release()

    assert await task == "shared"
    assert calls == 0
    module._in_flight_requests.clear()
    module._request_locks.clear()


@pytest.mark.asyncio
async def test_class_coalescer_rechecks_in_flight_after_waiting_for_existing_lock():
    coalescer = module.RequestCoalescer()
    lock = asyncio.Lock()
    await lock.acquire()
    coalescer._locks["race"] = lock
    loader = AsyncMock(return_value="unexpected")
    task = asyncio.create_task(coalescer.execute("race", loader))
    await asyncio.sleep(0)
    future = asyncio.get_running_loop().create_future()
    coalescer._in_flight["race"] = future
    future.set_result("shared")
    lock.release()

    assert await task == "shared"
    loader.assert_not_awaited()
    coalescer._in_flight.clear()
    coalescer._locks.clear()


@pytest.mark.asyncio
async def test_decorator_coalesces_concurrent_calls_and_supports_custom_key_builder():
    module._in_flight_requests.clear()
    module._request_locks.clear()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    @module.coalesce_requests()
    async def load(value: str) -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return value

    first = asyncio.create_task(load("value"))
    await started.wait()
    second = asyncio.create_task(load("value"))
    release.set()
    assert await asyncio.gather(first, second) == ["value", "value"]
    assert calls == 1

    custom_calls = 0

    @module.coalesce_requests(key_builder=lambda value: f"custom:{value}")
    async def custom(value: str) -> str:
        nonlocal custom_calls
        custom_calls += 1
        return value

    assert await custom("item") == "item"
    assert custom_calls == 1
    assert not module._in_flight_requests
    assert not module._request_locks


@pytest.mark.asyncio
async def test_decorator_propagates_error_and_cleans_global_state():
    module._in_flight_requests.clear()
    module._request_locks.clear()
    started = asyncio.Event()
    release = asyncio.Event()

    @module.coalesce_requests(prefix="failing")
    async def fail() -> None:
        started.set()
        await release.wait()
        raise RuntimeError("upstream failed")

    first = asyncio.create_task(fail())
    await started.wait()
    second = asyncio.create_task(fail())
    release.set()
    with pytest.raises(RuntimeError, match="upstream failed"):
        await asyncio.gather(first, second)
    assert not module._in_flight_requests
    assert not module._request_locks


@pytest.mark.asyncio
async def test_class_coalescer_shares_result_and_propagates_error():
    coalescer = module.RequestCoalescer(ttl_seconds=2.0)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def load() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "shared"

    first = asyncio.create_task(coalescer.execute("shared", load))
    await started.wait()
    second = asyncio.create_task(coalescer.execute("shared", load))
    release.set()
    assert await asyncio.gather(first, second) == ["shared", "shared"]
    assert calls == 1
    assert not coalescer._in_flight
    assert not coalescer._locks

    async def fail() -> None:
        raise RuntimeError("class failure")

    with pytest.raises(RuntimeError, match="class failure"):
        await coalescer.execute("failure", fail)
    assert not coalescer._in_flight
    assert not coalescer._locks
