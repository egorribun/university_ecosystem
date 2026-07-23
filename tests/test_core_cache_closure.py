from __future__ import annotations

from unittest.mock import AsyncMock, patch

import orjson
import pytest

from app.core.cache import LRUCache, MultiLayerCache, cached


def test_lru_update_and_prefix_invalidation_empty_result():
    cache = LRUCache[str](max_size=2)
    cache.set("key", "first")
    cache.set("key", "second")
    assert cache.get("key") == "second"
    assert cache.invalidate_prefix("missing:") == 0


@pytest.mark.asyncio
async def test_multilayer_l2_miss_and_metrics_guard_paths():
    redis = AsyncMock()
    redis.get.return_value = None
    cache = MultiLayerCache(redis_client=redis)
    assert await cache.get("missing") is None

    redis.get.side_effect = ConnectionError("redis unavailable")
    with patch("app.core.metrics.record_redis_command", side_effect=RuntimeError):
        assert await cache.get("error") is None

    redis.setex.side_effect = ConnectionError("redis unavailable")
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
