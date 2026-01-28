"""Tests for L1/L2 cache layer."""

import time

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
