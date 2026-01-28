"""Tests for L1/L2 cache layer."""

import time
from unittest.mock import AsyncMock

import pytest

from app.core.cache import (
    CacheEntry,
    LRUCache,
    MultiLayerCache,
    config_cache,
    schedule_cache,
    user_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_not_expired(self):
        """Test entry not expired."""
        entry = CacheEntry(value="test", expires_at=time.time() + 3600)
        assert entry.is_expired() is False

    def test_expired(self):
        """Test entry is expired."""
        entry = CacheEntry(value="test", expires_at=time.time() - 1)
        assert entry.is_expired() is True


class TestLRUCache:
    """Tests for LRUCache."""

    def test_set_and_get(self):
        """Test basic set and get."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        """Test get returns None for missing key."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        assert cache.get("nonexistent") is None

    def test_get_expired_key(self):
        """Test expired key returns None."""
        cache = LRUCache[str](max_size=10, default_ttl=0.001)
        cache.set("key1", "value1")
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_delete(self):
        """Test delete removes key."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_missing_key(self):
        """Test delete returns False for missing key."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        """Test clear removes all entries."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.size == 0

    def test_eviction_on_max_size(self):
        """Test LRU eviction when max size reached."""
        cache = LRUCache[str](max_size=3, default_ttl=60.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") == "value2"
        assert cache.size == 3

    def test_lru_order_on_get(self):
        """Test get moves item to end (most recently used)."""
        cache = LRUCache[str](max_size=3, default_ttl=60.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it most recently used
        cache.get("key1")

        # Add key4, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still exists
        assert cache.get("key2") is None  # Evicted

    def test_invalidate_prefix(self):
        """Test invalidate by prefix."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        cache.set("user:1", "alice")
        cache.set("user:2", "bob")
        cache.set("config:timeout", "30")

        count = cache.invalidate_prefix("user:")
        assert count == 2
        assert cache.get("user:1") is None
        assert cache.get("user:2") is None
        assert cache.get("config:timeout") == "30"

    def test_stats(self):
        """Test cache statistics."""
        cache = LRUCache[str](max_size=10, default_ttl=60.0)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestMultiLayerCache:
    """Tests for MultiLayerCache."""

    @pytest.mark.asyncio
    async def test_set_and_get_l1_only(self):
        """Test L1 cache without Redis."""
        cache = MultiLayerCache(l1_max_size=10, l1_ttl=60.0)
        await cache.set("key1", "value1")
        assert (await cache.get("key1")) == "value1"

    @pytest.mark.asyncio
    async def test_get_missing(self):
        """Test get returns None for missing key."""
        cache = MultiLayerCache(l1_max_size=10, l1_ttl=60.0)
        assert (await cache.get("nonexistent")) is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete from L1."""
        cache = MultiLayerCache(l1_max_size=10, l1_ttl=60.0)
        await cache.set("key1", "value1")
        await cache.delete("key1")
        assert (await cache.get("key1")) is None

    @pytest.mark.asyncio
    async def test_get_l2_hit_populates_l1(self):
        """Test L2 hit populates L1."""
        redis = AsyncMock()
        redis.get.return_value = "l2_value"
        cache = MultiLayerCache(redis_client=redis)

        # L1 miss, L2 hit
        val = await cache.get("key")
        assert val == "l2_value"
        # Verify L1 is now populated
        assert cache.l1.get("key") == "l2_value"

    @pytest.mark.asyncio
    async def test_get_l2_exception(self):
        """Test L2 exception doesn't crash get."""
        redis = AsyncMock()
        redis.get.side_effect = Exception("Redis error")
        cache = MultiLayerCache(redis_client=redis)

        # Should return None instead of crashing
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_set_l2_exception(self):
        """Test L2 exception doesn't crash set."""
        redis = AsyncMock()
        redis.setex.side_effect = Exception("Redis error")
        cache = MultiLayerCache(redis_client=redis)

        # Should not crash
        await cache.set("key", "val")
        assert cache.l1.get("key") == "val"

    @pytest.mark.asyncio
    async def test_delete_l2_exception(self):
        """Test L2 exception doesn't crash delete."""
        redis = AsyncMock()
        redis.delete.side_effect = Exception("Redis error")
        cache = MultiLayerCache(redis_client=redis)

        await cache.set("key", "val")
        # Should not crash
        await cache.delete("key")
        assert cache.l1.get("key") is None

    @pytest.mark.asyncio
    async def test_invalidate_prefix_l2_success(self):
        """Test L2 prefix invalidation success."""
        redis = AsyncMock()
        # Mock SCAN to return some keys then finish
        redis.scan.side_effect = [(1, ["p:1", "p:2"]), (0, ["p:3"])]
        cache = MultiLayerCache(redis_client=redis)
        cache.l1.set("p:1", "v1")
        cache.l1.set("other", "vo")

        count = await cache.invalidate_prefix("p:")
        assert count == 4  # 1 (L1) + 3 (L2)
        assert redis.delete.call_count == 2
        assert cache.l1.get("p:1") is None
        assert cache.l1.get("other") == "vo"

    @pytest.mark.asyncio
    async def test_invalidate_prefix_l2_exception(self):
        """Test L2 prefix invalidation exception."""
        redis = AsyncMock()
        redis.scan.side_effect = Exception("Redis error")
        cache = MultiLayerCache(redis_client=redis)
        cache.l1.set("p:1", "v1")

        # Should return L1 count even if L2 fails
        count = await cache.invalidate_prefix("p:")
        assert count == 1
        assert cache.l1.get("p:1") is None

    def test_stats(self):
        """Test stats method."""
        cache = MultiLayerCache(l1_max_size=10, l1_ttl=60.0)
        stats = cache.stats()
        assert "l1" in stats
        assert stats["l2_available"] is False


class TestGlobalCaches:
    """Test global cache instances."""

    def test_user_cache_exists(self):
        """Test user_cache singleton."""
        assert user_cache is not None
        assert isinstance(user_cache, LRUCache)

    def test_schedule_cache_exists(self):
        """Test schedule_cache singleton."""
        assert schedule_cache is not None
        assert isinstance(schedule_cache, LRUCache)

    def test_config_cache_exists(self):
        """Test config_cache singleton."""
        assert config_cache is not None
        assert isinstance(config_cache, LRUCache)
