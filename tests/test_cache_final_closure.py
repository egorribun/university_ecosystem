from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cache import LRUCache, MultiLayerCache
from app.core.cache_versioning import CacheVersionManager
from app.deps.cache import RedisCache


def test_lru_cache_expires_entries_evicts_oldest_and_reports_empty_rate():
    empty = LRUCache[str](max_size=1)
    assert empty.hit_rate == 0.0
    assert empty.stats()["hit_rate"] == 0.0

    cache = LRUCache[str](max_size=1)
    cache.set("old", "value")
    cache.set("new", "value")
    assert cache.get("old") is None
    assert cache.delete("new") is True
    cache.set("expired", "value", ttl=-1)
    assert cache.get("expired") is None
    assert cache.delete("missing") is False
    cache.clear()
    assert cache.size == 0


@pytest.mark.asyncio
async def test_multilayer_delete_and_prefix_scan_cover_redis_edges():
    redis = AsyncMock()
    cache = MultiLayerCache(redis_client=redis)
    cache.l1.set("item:one", 1)

    await cache.delete("item:one")
    redis.delete.assert_awaited_once_with("item:one")

    redis.delete.side_effect = ConnectionError("delete failed")
    await cache.delete("item:two")

    redis.delete.side_effect = None
    redis.scan.side_effect = [(1, [b"item:one"]), (0, [])]
    count = await cache.invalidate_prefix("item:")
    assert count == 1
    redis.delete.assert_awaited_with(b"item:one")

    redis.scan.side_effect = OSError("scan failed")
    assert await cache.invalidate_prefix("item:") == 0

    no_redis = MultiLayerCache()
    await no_redis.delete("missing")
    assert no_redis.stats()["l2_available"] is False


@pytest.mark.asyncio
async def test_cache_version_manager_handles_disabled_fallback_and_empty_value():
    manager = CacheVersionManager(prefix="events:list")
    disabled = MagicMock()
    disabled.enabled = False
    assert await manager.get_version(disabled) == "0"
    await manager.increment(disabled)
    await manager.reset(disabled)

    non_redis = MagicMock()
    non_redis.enabled = True
    assert await manager.get_version(non_redis) == "0"

    redis_cache = MagicMock(spec=RedisCache)
    redis_cache.enabled = True
    client = AsyncMock()
    client.get.return_value = None
    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        assert await manager.get_version(redis_cache) == "0"

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        side_effect=OSError("read failed"),
    ):
        assert await manager.get_version(redis_cache) == "0"


@pytest.mark.asyncio
async def test_cache_version_manager_increment_uses_get_set_fallback():
    manager = CacheVersionManager(prefix="news:list")
    redis_cache = MagicMock(spec=RedisCache)
    redis_cache.enabled = True
    client = SimpleNamespace(get=AsyncMock(return_value=b"4"), set=AsyncMock())

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        await manager.increment(redis_cache)

    client.get.assert_awaited_once_with("news:list:version")
    client.set.assert_awaited_once_with("news:list:version", "5")

    client_with_incr = SimpleNamespace(incr=AsyncMock())
    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client_with_incr,
    ):
        await manager.increment(redis_cache)
    client_with_incr.incr.assert_awaited_once_with("news:list:version")
