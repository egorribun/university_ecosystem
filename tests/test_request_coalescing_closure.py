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
