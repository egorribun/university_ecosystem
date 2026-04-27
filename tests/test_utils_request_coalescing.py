"""Unit tests for app/utils/request_coalescing.py.

Tests the coalesce_requests decorator and RequestCoalescer class
using asyncio without any database or HTTP fixtures.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.utils.request_coalescing import (
    RequestCoalescer,
    _build_request_key,
    coalesce_requests,
)


# ---------------------------------------------------------------------------
# _build_request_key
# ---------------------------------------------------------------------------
class TestBuildRequestKey:
    def test_returns_hex_string(self) -> None:
        key = _build_request_key("prefix", 1, 2)
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex digest

    def test_same_args_produce_same_key(self) -> None:
        key1 = _build_request_key("p", 1, 2, x=3)
        key2 = _build_request_key("p", 1, 2, x=3)
        assert key1 == key2

    def test_different_args_produce_different_keys(self) -> None:
        key1 = _build_request_key("p", 1)
        key2 = _build_request_key("p", 2)
        assert key1 != key2

    def test_different_prefixes_produce_different_keys(self) -> None:
        key1 = _build_request_key("a", 1)
        key2 = _build_request_key("b", 1)
        assert key1 != key2

    def test_kwargs_are_sorted_deterministically(self) -> None:
        key1 = _build_request_key("p", a=1, b=2)
        key2 = _build_request_key("p", b=2, a=1)
        assert key1 == key2


# ---------------------------------------------------------------------------
# coalesce_requests decorator
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCoalesceRequests:
    async def test_basic_call_executes_function(self) -> None:
        @coalesce_requests(prefix="test")
        async def fetch(value: int) -> int:
            return value * 2

        assert await fetch(5) == 10

    async def test_concurrent_identical_calls_execute_once(self) -> None:
        call_count = 0

        @coalesce_requests(prefix="heavy")
        async def expensive(value: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # simulate I/O
            return value

        results = await asyncio.gather(expensive(42), expensive(42), expensive(42))
        assert results == [42, 42, 42]
        # The underlying function must have been called only once
        assert call_count == 1

    async def test_different_args_execute_separately(self) -> None:
        call_count = 0

        @coalesce_requests(prefix="multi")
        async def fetch(value: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return value

        results = await asyncio.gather(fetch(1), fetch(2))
        assert set(results) == {1, 2}
        assert call_count == 2

    async def test_exception_propagates_to_all_waiters(self) -> None:
        @coalesce_requests(prefix="fail")
        async def failing() -> int:
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await asyncio.gather(failing(), failing())

    async def test_custom_key_builder_is_used(self) -> None:
        call_count = 0

        def my_key_builder(*args, **kwargs) -> str:
            return "constant-key"

        @coalesce_requests(key_builder=my_key_builder)
        async def fetch(value: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return value

        results = await asyncio.gather(fetch(1), fetch(2))
        # Both calls share the same key → executed once
        assert call_count == 1
        # Both receive the same result (the first's return)
        assert results[0] == results[1]

    async def test_state_cleared_after_call(self) -> None:
        """A second call after the first completes should execute again."""
        call_count = 0

        @coalesce_requests(prefix="state_clear")
        async def fetch() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        r1 = await fetch()
        r2 = await fetch()
        assert call_count == 2
        assert r1 == 1
        assert r2 == 2

    async def test_function_name_used_as_default_prefix(self) -> None:
        """When no prefix is given, the function name should be the prefix."""
        call_count = 0

        @coalesce_requests()
        async def named_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            # A yield point is required so that asyncio.gather can start both
            # coroutines before the first one completes and registers a future.
            await asyncio.sleep(0)
            return x

        r1, r2 = await asyncio.gather(named_function(7), named_function(7))
        assert r1 == r2 == 7
        assert call_count == 1


# ---------------------------------------------------------------------------
# RequestCoalescer (class-based)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestRequestCoalescer:
    async def test_execute_returns_result(self) -> None:
        coalescer = RequestCoalescer()
        result = await coalescer.execute("k1", AsyncMock(return_value=99))
        assert result == 99

    async def test_concurrent_calls_with_same_key_execute_once(self) -> None:
        call_count = 0
        coalescer = RequestCoalescer()

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return "value"

        results = await asyncio.gather(
            coalescer.execute("shared", fn),
            coalescer.execute("shared", fn),
            coalescer.execute("shared", fn),
        )
        assert results == ["value", "value", "value"]
        assert call_count == 1

    async def test_concurrent_calls_with_different_keys_execute_independently(
        self,
    ) -> None:
        call_count = 0
        coalescer = RequestCoalescer()

        async def fn(label: str) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return label

        r1, r2 = await asyncio.gather(
            coalescer.execute("k1", lambda: fn("a")),
            coalescer.execute("k2", lambda: fn("b")),
        )
        assert r1 == "a"
        assert r2 == "b"
        assert call_count == 2

    async def test_exception_propagates_to_all_waiters(self) -> None:
        coalescer = RequestCoalescer()

        async def failing() -> None:
            await asyncio.sleep(0.01)
            raise RuntimeError("coalescer failure")

        with pytest.raises(RuntimeError, match="coalescer failure"):
            await asyncio.gather(
                coalescer.execute("fail", failing),
                coalescer.execute("fail", failing),
            )

    async def test_state_is_cleared_after_completion(self) -> None:
        coalescer = RequestCoalescer()
        fn = AsyncMock(return_value="ok")

        await coalescer.execute("key", fn)
        await coalescer.execute("key", fn)

        assert fn.call_count == 2
