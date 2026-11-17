from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import orjson
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusyLoadingError,
    DataError,
    NoPermissionError,
    ResponseError,
)
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.cache import LRUCache, MultiLayerCache, cached


def test_lru_update_and_prefix_invalidation_empty_result():
    cache = LRUCache[str](max_size=2)
    cache.set("key", "first")
    cache.set("key", "second")
    assert cache.get("key") == "second"
    assert cache.invalidate_prefix("missing:") == 0

    expired = LRUCache[str](max_size=1)
    expired.set("expired", "value", ttl=-1)
    assert expired.get("expired") is None

    evicted = LRUCache[str](max_size=1)
    evicted.set("first", "value")
    evicted.set("second", "value")
    assert evicted.get("first") is None
    assert evicted.delete("second") is True
    assert evicted.delete("second") is False
    evicted.clear()
    assert evicted.size == 0
    assert evicted.hit_rate == 0.0
    assert evicted.stats()["size"] == 0
    assert LRUCache[str]().hit_rate == 0.0


@pytest.mark.asyncio
async def test_multilayer_l2_miss_and_metrics_guard_paths():
    redis = AsyncMock()
    redis.get.return_value = None
    cache = MultiLayerCache(redis_client=redis)
    assert await cache.get("missing") is None

    redis.get.side_effect = ConnectionError("redis unavailable")
    with patch("app.core.metrics.record_redis_command", side_effect=RuntimeError):
        assert await cache.get("error") is None

    redis.set.side_effect = ConnectionError("redis unavailable")
    with patch("app.core.metrics.record_redis_command", side_effect=RuntimeError):
        await cache.set("error", {"value": 1})


@pytest.mark.asyncio
async def test_multilayer_prefix_scan_handles_empty_batch_and_no_redis():
    redis = AsyncMock()
    redis.scan.return_value = (0, [])
    cache = MultiLayerCache(redis_client=redis)
    assert await cache.invalidate_prefix("empty:") == 0
    redis.delete.assert_not_awaited()

    no_redis = MultiLayerCache()
    no_redis.l1.set("prefix:key", "value")
    assert await no_redis.invalidate_prefix("prefix:") == 1
    await no_redis.delete("prefix:key")

    paged_redis = AsyncMock()
    paged_redis.scan.side_effect = [(1, []), (0, ["prefix:remote"])]
    paged = MultiLayerCache(redis_client=paged_redis)
    paged.l1.set("prefix:local", "value")
    assert await paged.invalidate_prefix("prefix:") == 2
    paged_redis.delete.assert_awaited_once_with("prefix:remote")

    failing_redis = AsyncMock()
    failing_redis.scan.side_effect = ConnectionError("redis unavailable")
    failing = MultiLayerCache(redis_client=failing_redis)
    assert await failing.invalidate_prefix("prefix:") == 0


@pytest.mark.asyncio
async def test_multilayer_delete_and_l2_set_success_and_failure():
    redis = AsyncMock()
    cache = MultiLayerCache(redis_client=redis, l2_ttl=11)
    await cache.set("key", {"value": 1}, l1_ttl=3)
    redis.set.assert_awaited_once_with("key", b'{"value":1}', ex=11)
    await cache.delete("key")
    redis.delete.assert_awaited_once_with("key")

    redis.delete.side_effect = ConnectionError("redis unavailable")
    await cache.delete("missing")
    assert cache.stats()["l2_available"] is True


@pytest.mark.asyncio
async def test_cached_decorator_covers_lru_hit_miss_and_none_result():
    cache = LRUCache[str]()
    calls = 0

    @cached(cache, lambda value: f"value:{value}", ttl=10)
    async def load(value: str) -> str:
        nonlocal calls
        calls += 1
        return value.upper()

    assert await load("a") == "A"
    assert await load("a") == "A"
    assert calls == 1

    @cached(cache, lambda value: f"none:{value}")
    async def empty(value: str) -> None:
        return None

    assert await empty("a") is None
    assert cache.get("none:a") is None


@pytest.mark.asyncio
async def test_cached_decorator_covers_multilayer_set_and_hit():
    cache = MultiLayerCache()
    calls = 0

    @cached(cache, lambda value: f"multi:{value}", ttl=7)
    async def load(value: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"value": value}

    assert await load("a") == {"value": "a"}
    assert await load("a") == {"value": "a"}
    assert calls == 1

    redis = AsyncMock()
    redis.get.return_value = orjson.dumps({"value": "from-l2"})
    l2_cache = MultiLayerCache(redis_client=redis)
    assert await l2_cache.get("l2") == {"value": "from-l2"}


@pytest.mark.asyncio
async def test_cached_decorator_with_l1_ttl():
    cache = MultiLayerCache()
    calls = 0

    @cached(cache, lambda value: f"l1_ttl:{value}", ttl=300, _l1_ttl=60)
    async def load(value: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"value": value}

    assert await load("b") == {"value": "b"}
    assert await load("b") == {"value": "b"}
    assert calls == 1

    # Also test LRUCache with _l1_ttl
    lru = LRUCache[dict[str, str]]()
    lru_calls = 0

    @cached(lru, lambda value: f"lru:{value}", _l1_ttl=30)
    async def load_lru(value: str) -> dict[str, str]:
        nonlocal lru_calls
        lru_calls += 1
        return {"value": value}

    assert await load_lru("c") == {"value": "c"}
    assert await load_lru("c") == {"value": "c"}
    assert lru_calls == 1


async def _invoke_l2_operation(cache, operation):
    if operation == "get":
        return await cache.get("prefix:key")
    if operation == "set":
        return await cache.set("prefix:key", {"value": 1})
    if operation == "delete":
        return await cache.delete("prefix:key")
    return await cache.invalidate_prefix("prefix:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [
        RedisConnectionError,
        RedisTimeoutError,
        BusyLoadingError,
    ],
)
@pytest.mark.parametrize("operation", ["get", "set", "delete", "scan", "scan-delete"])
async def test_multilayer_real_redis_transport_errors_fail_soft(
    error_type, operation, caplog
):
    redis = AsyncMock()
    redis.scan.return_value = (0, [b"prefix:remote"])
    method = "delete" if operation == "scan-delete" else operation
    getattr(redis, method).side_effect = error_type("private-redis-endpoint-marker")
    cache = MultiLayerCache(redis_client=redis)
    if operation not in {"get", "set"}:
        cache.l1.set("prefix:key", "old")
    with patch("app.core.metrics.record_redis_command") as metric:
        result = await _invoke_l2_operation(cache, operation)
    getattr(redis, method).assert_awaited_once()
    if operation in {"scan", "scan-delete"}:
        assert result == 1
    else:
        assert result is None
    if operation == "set":
        assert cache.l1.get("prefix:key") == {"value": 1}
    else:
        assert cache.l1.get("prefix:key") is None
    if operation in {"get", "set"}:
        metric.assert_called_once_with(operation, 0.0, success=False)
    assert "private-redis-endpoint-marker" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [
        AuthenticationError,
        AuthorizationError,
        ResponseError,
        NoPermissionError,
        DataError,
        ValueError,
        asyncio.CancelledError,
    ],
)
@pytest.mark.parametrize("operation", ["get", "set", "delete", "scan", "scan-delete"])
async def test_multilayer_nontransport_errors_and_cancellation_propagate(
    error_type, operation
):
    redis = AsyncMock()
    redis.scan.return_value = (0, [b"prefix:remote"])
    method = "delete" if operation == "scan-delete" else operation
    error = error_type("synthetic failure")
    getattr(redis, method).side_effect = error
    cache = MultiLayerCache(redis_client=redis)
    with pytest.raises(error_type) as caught:
        await _invoke_l2_operation(cache, operation)
    assert caught.value is error


@pytest.mark.asyncio
async def test_cached_source_recovers_after_real_redis_transport_failure():
    redis = AsyncMock()
    redis.get.side_effect = RedisConnectionError("unavailable")
    redis.set.side_effect = RedisTimeoutError("unavailable")
    cache = MultiLayerCache(redis_client=redis)
    source = AsyncMock(return_value={"value": "source"})

    @cached(cache, lambda: "key")
    async def load():
        return await source()

    assert await load() == {"value": "source"}
    assert await load() == {"value": "source"}
    source.assert_awaited_once()
    redis.get.assert_awaited_once_with("key")
    redis.set.assert_awaited_once()
