import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deps.cache import (
    CacheEntry,
    MemoryCache,
    NullCache,
    RedisCache,
    TieredCache,
    cached,
    etag_matches,
    format_etag,
    get_cache_key_version,
    set_cache_key_version,
    stale_while_revalidate,
    versioned_key,
)


# 1. CacheEntry Tests
def test_cache_entry_should_refresh_probabilistic():
    now = time.time()
    # Expired entry
    entry = CacheEntry(
        etag="123", payload="data", stored_at=now - 100, ttl_seconds=60.0
    )
    assert entry.should_refresh_probabilistic() is True

    # Fresh entry, beta=0 (no probabilistic refresh)
    entry = CacheEntry(etag="123", payload="data", stored_at=now - 30, ttl_seconds=60.0)
    assert entry.should_refresh_probabilistic(beta=0.0) is False

    # Negative TTL
    entry = CacheEntry(etag="123", payload="data", stored_at=now, ttl_seconds=-1.0)
    assert entry.should_refresh_probabilistic() is False


# 2. NullCache Tests
@pytest.mark.asyncio
async def test_null_cache():
    cache = NullCache()
    assert cache.enabled is False
    await cache.set("key", "val")
    assert await cache.get("key") is None
    await cache.invalidate("key")
    await cache.close()


# 3. MemoryCache Tests
@pytest.mark.asyncio
async def test_memory_cache_get_set():
    cache = MemoryCache(default_ttl=60)
    await cache.set("key1", "val1")
    entry = await cache.get("key1")
    assert entry is not None
    assert entry.payload == "val1"
    assert entry.ttl_seconds == 60.0


@pytest.mark.asyncio
async def test_memory_cache_expiry():
    cache = MemoryCache(default_ttl=1)
    await cache.set("key1", "val1")
    # Mock time.time() to simulate expiry
    with patch("time.time", return_value=time.time() + 10):
        assert await cache.get("key1") is None


@pytest.mark.asyncio
async def test_memory_cache_eviction():
    cache = MemoryCache(max_size=10)  # Minimum enforced size in app/deps/cache.py is 10
    for i in range(11):
        await cache.set(f"k{i}", f"v{i}")

    # k0 should be evicted as it was added first and not accessed
    assert await cache.get("k0") is None
    assert (await cache.get("k1")).payload == "v1"
    assert (await cache.get("k10")).payload == "v10"


@pytest.mark.asyncio
async def test_memory_cache_invalidate():
    cache = MemoryCache()
    await cache.set("user:1", "v1")
    await cache.set("user:2", "v2")
    await cache.set("post:1", "v3")

    await cache.invalidate("user:*")
    assert await cache.get("user:1") is None
    assert await cache.get("user:2") is None
    assert (await cache.get("post:1")).payload == "v3"


# 4. RedisCache Tests
@pytest.mark.asyncio
async def test_redis_cache_get_set():
    with patch("app.deps.cache.Redis", autospec=True) as mock_redis_cls:
        mock_redis = mock_redis_cls.from_url.return_value
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        cache = RedisCache("redis://localhost", default_ttl=60)
        assert await cache.get("key1") is None

        # Mock hit
        from app.deps.cache import orjson

        entry_data = {
            "etag": "e1",
            "payload": "v1",
            "stored_at": time.time(),
            "ttl_seconds": 60.0,
        }
        mock_redis.get.return_value = orjson.dumps(entry_data).decode()

        res = await cache.get("key1")
        assert res.payload == "v1"
        assert res.etag == "e1"

        await cache.set("key2", "v2")
        mock_redis.set.assert_called()


# 5. TieredCache Tests
@pytest.mark.asyncio
async def test_tiered_cache():
    l1 = MemoryCache()
    l2 = MemoryCache()
    tiered = TieredCache(l1, l2)

    await tiered.set("k1", "v1")
    assert (await l1.get("k1")).payload == "v1"
    assert (await l2.get("k1")).payload == "v1"

    await l1.invalidate("k1")
    # Should backfill L1 from L2
    assert (await tiered.get("k1")).payload == "v1"
    assert (await l1.get("k1")).payload == "v1"


# 6. Decorator Tests
@pytest.mark.asyncio
async def test_cached_decorator():
    mock_cache = MagicMock(spec=MemoryCache)
    mock_cache.enabled = True
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    with patch("app.deps.cache.get_cache", return_value=mock_cache):

        @cached(ttl=60)
        async def my_func(x):
            return x * 2

        assert await my_func(5) == 10
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_swr_decorator():
    mock_cache = MagicMock(spec=MemoryCache)
    mock_cache.enabled = True

    # Mock stale entry
    entry = CacheEntry(
        etag="e", payload="stale", stored_at=time.time() - 100, ttl_seconds=200.0
    )
    mock_cache.get = AsyncMock(return_value=entry)
    mock_cache.set = AsyncMock()

    with patch("app.deps.cache.get_cache", return_value=mock_cache):

        @stale_while_revalidate(ttl=60, stale_ttl=120)
        async def my_func():
            return "fresh"

        res = await my_func()
        assert res == "stale"
        # Since it's stale, a background task should be created to refresh
        await asyncio.sleep(0.1)
        # Note: We can't easily assert the background task results without more complex mocks,
        # but the flow is covered.


# 7. Utilities
def test_key_versioning():
    set_cache_key_version(2)
    assert get_cache_key_version() == 2
    assert versioned_key("mykey") == "v2:mykey"


def test_etag_matching():
    assert etag_matches("abc", '"abc"') is True
    assert etag_matches("abc", 'W/"abc"') is True
    assert etag_matches("abc", "*") is True
    assert etag_matches("abc", '"xyz", "abc"') is True
    assert etag_matches("abc", "xyz") is False
    assert format_etag("abc") == '"abc"'
    assert format_etag('"abc"') == '"abc"'
