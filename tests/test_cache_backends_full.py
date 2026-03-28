"""Comprehensive tests for app/deps/cache.py backends and utilities.

Covers: RedisClusterCache, create_cache_backend() branches, TieredCache
edge cases, decorator key_builder paths, cache utilities, and pattern
invalidation via SCAN.
"""

from __future__ import annotations

import time as time_module
from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.deps.cache import (
    CacheEntry,
    MemoryCache,
    NullCache,
    RedisCache,
    RedisClusterCache,
    TieredCache,
    _json_default,
    _normalize_payload,
    cached,
    create_cache_backend,
    etag_matches,
    format_etag,
    get_cache,
    get_cache_client,
    get_cache_key_version,
    set_cache_backend,
    set_cache_key_version,
    shutdown_cache,
    stale_while_revalidate,
    versioned_key,
)

# ---------------------------------------------------------------------------
# RedisClusterCache
# ---------------------------------------------------------------------------


class TestRedisClusterCache:
    """Tests for the entirely uncovered RedisClusterCache backend."""

    @pytest.fixture
    def cluster_cache(self) -> RedisClusterCache:
        return RedisClusterCache(url="redis://localhost:6379/0", default_ttl=60)

    @pytest.mark.asyncio
    async def test_init(self, cluster_cache: RedisClusterCache):
        assert cluster_cache.enabled is True
        assert cluster_cache._client is None
        assert cluster_cache._default_ttl == 60

    @pytest.mark.asyncio
    async def test_get_client_fallback_to_single_redis(self, cluster_cache):
        """When redis.asyncio.cluster is not importable, falls back to single Redis."""
        fake_client = fakeredis.aioredis.FakeRedis(decode_responses=True)

        with patch("app.deps.cache.Redis.from_url", return_value=fake_client):
            with patch.dict("sys.modules", {"redis.asyncio.cluster": None}):
                # Force ImportError path
                original_import = (
                    __builtins__.__import__
                    if hasattr(__builtins__, "__import__")
                    else __import__
                )

                def mock_import(name, *args, **kwargs):
                    if name == "redis.asyncio.cluster":
                        raise ImportError("No cluster module")
                    return original_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=mock_import):
                    client = await cluster_cache._get_client()
                    assert client is not None

        await cluster_cache.close()

    @pytest.mark.asyncio
    async def test_get_set_roundtrip(self, cluster_cache):
        """Basic get/set roundtrip with mocked client."""
        fake_client = AsyncMock()
        fake_client.get = AsyncMock(return_value=None)
        fake_client.set = AsyncMock()
        cluster_cache._client = fake_client

        # Set
        entry = await cluster_cache.set("test:key", {"hello": "world"}, ttl=30)
        assert entry.etag
        assert entry.payload == {"hello": "world"}
        fake_client.set.assert_called_once()

        # Get miss
        result = await cluster_cache.get("test:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_cached_entry(self, cluster_cache):
        """Get returns valid CacheEntry when data exists."""
        import orjson

        stored = orjson.dumps(
            {
                "etag": "abc123",
                "payload": {"data": "value"},
                "stored_at": time_module.time(),
                "ttl_seconds": 60.0,
            }
        ).decode("utf-8")

        fake_client = AsyncMock()
        fake_client.get = AsyncMock(return_value=stored)
        cluster_cache._client = fake_client

        result = await cluster_cache.get("test:key")
        assert result is not None
        assert result.etag == "abc123"
        assert result.payload == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_json_decode_error(self, cluster_cache):
        """Invalid JSON returns None."""
        fake_client = AsyncMock()
        fake_client.get = AsyncMock(return_value="not-valid-json{{{")
        cluster_cache._client = fake_client

        result = await cluster_cache.get("bad:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_error(self, cluster_cache):
        """RedisError returns None gracefully."""
        from redis.exceptions import RedisError

        fake_client = AsyncMock()
        fake_client.get = AsyncMock(side_effect=RedisError("Connection lost"))
        cluster_cache._client = fake_client

        result = await cluster_cache.get("error:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_redis_error(self, cluster_cache):
        """Set handles RedisError gracefully, still returns CacheEntry."""
        from redis.exceptions import RedisError

        fake_client = AsyncMock()
        fake_client.set = AsyncMock(side_effect=RedisError("Write failed"))
        cluster_cache._client = fake_client

        entry = await cluster_cache.set("fail:key", {"data": 1})
        assert entry is not None
        assert entry.payload == {"data": 1}

    @pytest.mark.asyncio
    async def test_set_without_ttl(self, cluster_cache):
        fake_client = AsyncMock()
        fake_client.set = AsyncMock()
        cluster_cache._client = fake_client
        cluster_cache._default_ttl = 0

        await cluster_cache.set("no-ttl", {"x": 1}, ttl=0)
        # Should call set without ex parameter
        call_kwargs = fake_client.set.call_args
        assert "ex" not in (call_kwargs.kwargs if call_kwargs.kwargs else {})

    @pytest.mark.asyncio
    async def test_invalidate_exact_keys(self, cluster_cache):
        """Invalidate deletes exact keys (no patterns)."""
        fake_client = AsyncMock()
        fake_client.delete = AsyncMock()
        cluster_cache._client = fake_client

        await cluster_cache.invalidate("key1", "key2")
        fake_client.delete.assert_called_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_invalidate_skips_patterns(self, cluster_cache):
        """Cluster cache handles pattern keys via SCAN (TD-33-10)."""
        fake_client = AsyncMock()
        fake_client.delete = AsyncMock()
        # SCAN returns (cursor, matches); cursor=0 means done
        fake_client.scan = AsyncMock(return_value=(0, []))
        cluster_cache._client = fake_client

        await cluster_cache.invalidate("key:*", "exact:key")
        # Exact key deleted, pattern processed via SCAN (no matches found)
        fake_client.delete.assert_called_once_with("exact:key")

    @pytest.mark.asyncio
    async def test_invalidate_empty(self, cluster_cache):
        """Empty invalidation is a noop."""
        fake_client = AsyncMock()
        cluster_cache._client = fake_client

        await cluster_cache.invalidate()
        # Should not even get client

    @pytest.mark.asyncio
    async def test_invalidate_redis_error(self, cluster_cache):
        """RedisError in invalidation is handled gracefully."""
        from redis.exceptions import RedisError

        fake_client = AsyncMock()
        fake_client.delete = AsyncMock(side_effect=RedisError("fail"))
        cluster_cache._client = fake_client

        # Should not raise
        await cluster_cache.invalidate("key1")

    @pytest.mark.asyncio
    async def test_close(self, cluster_cache):
        """Close disposes client."""
        fake_client = AsyncMock()
        fake_client.aclose = AsyncMock()
        cluster_cache._client = fake_client

        await cluster_cache.close()
        assert cluster_cache._client is None
        fake_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self, cluster_cache):
        """Close with no client is a noop."""
        await cluster_cache.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_error(self, cluster_cache):
        """Close handles errors gracefully."""
        fake_client = AsyncMock()
        fake_client.aclose = AsyncMock(side_effect=OSError("socket closed"))
        cluster_cache._client = fake_client

        await cluster_cache.close()  # Should not raise
        assert cluster_cache._client is None

    def test_resolve_ttl(self, cluster_cache):
        assert cluster_cache._resolve_ttl(None) == 60  # default
        assert cluster_cache._resolve_ttl(120) == 120
        assert cluster_cache._resolve_ttl(0) == 0
        assert cluster_cache._resolve_ttl(-5) == 0


# ---------------------------------------------------------------------------
# create_cache_backend() configuration branches
# ---------------------------------------------------------------------------


class TestCreateCacheBackend:
    def test_disabled_returns_null(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", False)
        backend = create_cache_backend()
        assert isinstance(backend, NullCache)

    def test_memory_backend(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "memory")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        monkeypatch.setattr(settings, "cache_default_ttl_seconds", 300)
        backend = create_cache_backend()
        assert isinstance(backend, MemoryCache)

    def test_redis_backend(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "redis")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        monkeypatch.setattr(settings, "cache_redis_url", "redis://localhost:6379/0")
        monkeypatch.setattr(settings, "cache_default_ttl_seconds", 60)
        backend = create_cache_backend()
        assert isinstance(backend, RedisCache)

    def test_redis_backend_no_url(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "redis")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        monkeypatch.setattr(settings, "cache_redis_url", "")
        backend = create_cache_backend()
        assert isinstance(backend, NullCache)

    def test_tiered_backend(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "tiered")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        monkeypatch.setattr(settings, "cache_redis_url", "redis://localhost:6379/0")
        monkeypatch.setattr(settings, "cache_default_ttl_seconds", 60)
        monkeypatch.setattr(settings, "cache_l1_ttl_seconds", 30)
        backend = create_cache_backend()
        assert isinstance(backend, TieredCache)

    def test_tiered_backend_no_l2_url(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "tiered")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        monkeypatch.setattr(settings, "cache_redis_url", "")
        backend = create_cache_backend()
        # Falls back to L1 only (MemoryCache)
        assert isinstance(backend, MemoryCache)

    def test_unknown_backend(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "cache_enabled", True)
        monkeypatch.setattr(settings, "cache_backend", "unknown_backend")
        if hasattr(settings, "cache_backend_normalized"):
            monkeypatch.setattr(settings, "cache_backend_normalized", None)
        backend = create_cache_backend()
        assert isinstance(backend, NullCache)


# ---------------------------------------------------------------------------
# TieredCache edge cases
# ---------------------------------------------------------------------------


class TestTieredCacheEdgeCases:
    @pytest.mark.asyncio
    async def test_both_miss(self):
        """Both L1 and L2 miss returns None."""
        l1 = NullCache()
        l2 = NullCache()
        tiered = TieredCache(l1, l2)

        result = await tiered.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_l2_hit_backfills_l1(self):
        """L2 hit backfills L1."""
        l1 = MemoryCache(default_ttl=60)
        l2 = MemoryCache(default_ttl=60)
        tiered = TieredCache(l1, l2)

        # Set only in L2
        await l2.set("key", {"value": 42})

        # Get via tiered — should backfill L1
        result = await tiered.get("key")
        assert result is not None
        assert result.payload == {"value": 42}

        # Verify L1 now has the entry
        l1_entry = await l1.get("key")
        assert l1_entry is not None

    @pytest.mark.asyncio
    async def test_invalidate_both_layers(self):
        l1 = MemoryCache(default_ttl=60)
        l2 = MemoryCache(default_ttl=60)
        tiered = TieredCache(l1, l2)

        await tiered.set("key", "val")
        await tiered.invalidate("key")

        assert await l1.get("key") is None
        assert await l2.get("key") is None

    @pytest.mark.asyncio
    async def test_close_both_layers(self):
        l1 = MemoryCache()
        l2 = MemoryCache()
        tiered = TieredCache(l1, l2)

        # Should not raise
        await tiered.close()


# ---------------------------------------------------------------------------
# RedisCache — pattern invalidation via SCAN
# ---------------------------------------------------------------------------


class TestRedisCachePatternInvalidation:
    @pytest.mark.asyncio
    async def test_pattern_invalidation_via_scan(self):
        """Pattern keys use SCAN to find and delete matching keys."""
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis

        # Set up test data
        await fake_redis.set("prefix:key1", "v1")
        await fake_redis.set("prefix:key2", "v2")
        await fake_redis.set("other:key3", "v3")

        await cache.invalidate("prefix:*")

        assert await fake_redis.get("prefix:key1") is None
        assert await fake_redis.get("prefix:key2") is None
        assert await fake_redis.get("other:key3") == "v3"

        await cache.close()

    @pytest.mark.asyncio
    async def test_empty_invalidation(self):
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fakeredis.aioredis.FakeRedis(decode_responses=True)

        # Should not raise
        await cache.invalidate()
        await cache.close()

    @pytest.mark.asyncio
    async def test_mixed_exact_and_pattern(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis

        await fake_redis.set("exact:key", "v1")
        await fake_redis.set("pattern:a", "v2")
        await fake_redis.set("pattern:b", "v3")

        await cache.invalidate("exact:key", "pattern:*")

        assert await fake_redis.get("exact:key") is None
        assert await fake_redis.get("pattern:a") is None
        assert await fake_redis.get("pattern:b") is None

        await cache.close()


# ---------------------------------------------------------------------------
# RedisCache — close edge cases
# ---------------------------------------------------------------------------


class TestRedisCacheClose:
    @pytest.mark.asyncio
    async def test_close_with_aclose(self):
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        fake = AsyncMock()
        fake.aclose = AsyncMock()
        cache._client = fake

        await cache.close()
        assert cache._client is None
        fake.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_sync_close(self):
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        fake = MagicMock()
        del fake.aclose  # Remove aclose to trigger close() path
        fake.close = MagicMock(return_value=None)
        cache._client = fake

        await cache.close()
        assert cache._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        await cache.close()  # noop

    @pytest.mark.asyncio
    async def test_close_with_error(self):
        from redis.exceptions import RedisError

        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        fake = AsyncMock()
        fake.aclose = AsyncMock(side_effect=RedisError("fail"))
        cache._client = fake

        await cache.close()  # Should not raise
        assert cache._client is None


# ---------------------------------------------------------------------------
# RedisCache — get/set error paths
# ---------------------------------------------------------------------------


class TestRedisCacheErrors:
    @pytest.mark.asyncio
    async def test_get_json_decode_error(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis

        await fake_redis.set("bad:json", "not{valid{json")
        result = await cache.get("bad:json")
        assert result is None

        # Key should be invalidated
        assert await fake_redis.get("bad:json") is None
        await cache.close()

    @pytest.mark.asyncio
    async def test_get_redis_error(self):
        from redis.exceptions import RedisError

        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        fake = AsyncMock()
        fake.get = AsyncMock(side_effect=RedisError("connection lost"))
        cache._client = fake

        result = await cache.get("err:key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_redis_error(self):
        from redis.exceptions import RedisError

        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        fake = AsyncMock()
        fake.set = AsyncMock(side_effect=RedisError("write failed"))
        cache._client = fake

        entry = await cache.set("err:key", {"data": 1})
        # Still returns a CacheEntry even on error
        assert entry is not None
        assert entry.payload == {"data": 1}

    @pytest.mark.asyncio
    async def test_set_without_ttl(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=0)
        cache._client = fake_redis

        entry = await cache.set("no-ttl", {"x": 1}, ttl=0)
        assert entry.payload == {"x": 1}
        await cache.close()

    @pytest.mark.asyncio
    async def test_get_missing_stored_at(self):
        """When stored_at is missing or 0, falls back to current time."""
        import orjson

        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis

        envelope = orjson.dumps(
            {
                "etag": "test-etag",
                "payload": {"data": 1},
                "stored_at": 0,
                "ttl_seconds": 60.0,
            }
        ).decode("utf-8")
        await fake_redis.set("missing-ts", envelope)

        result = await cache.get("missing-ts")
        assert result is not None
        assert result.stored_at > 0  # Should be current time
        await cache.close()


# ---------------------------------------------------------------------------
# Decorators — key_builder and edge cases
# ---------------------------------------------------------------------------


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_with_custom_key_builder(self):
        """Custom key_builder is used instead of default."""
        mem = MemoryCache(default_ttl=60)
        set_cache_backend(mem)

        call_count = 0

        @cached(prefix="test", key_builder=lambda x: f"custom:{x}")
        async def my_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await my_func(5)
        assert result1 == 10
        assert call_count == 1

        result2 = await my_func(5)
        assert result2 == 10
        assert call_count == 1  # Cached

        set_cache_backend(None)

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """When cache is disabled, always calls the function."""
        set_cache_backend(NullCache())

        call_count = 0

        @cached(prefix="test")
        async def my_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        await my_func(5)
        await my_func(5)
        assert call_count == 2  # No caching

        set_cache_backend(None)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_payload(self):
        mem = MemoryCache(default_ttl=60)
        set_cache_backend(mem)

        @cached(prefix="hit")
        async def my_func(a: str) -> str:
            return f"computed:{a}"

        r1 = await my_func("x")
        assert r1 == "computed:x"

        r2 = await my_func("x")
        assert r2 == "computed:x"

        set_cache_backend(None)


class TestSWRDecorator:
    @pytest.mark.asyncio
    async def test_swr_cache_miss(self):
        """On cache miss, computes and stores."""
        mem = MemoryCache(default_ttl=300)
        set_cache_backend(mem)

        @stale_while_revalidate(prefix="swr", ttl=60, stale_ttl=120)
        async def my_func(x: int) -> int:
            return x + 1

        result = await my_func(10)
        assert result == 11

        set_cache_backend(None)

    @pytest.mark.asyncio
    async def test_swr_disabled_cache(self):
        set_cache_backend(NullCache())

        call_count = 0

        @stale_while_revalidate(prefix="swr", ttl=10)
        async def my_func() -> str:
            nonlocal call_count
            call_count += 1
            return "fresh"

        await my_func()
        await my_func()
        assert call_count == 2  # No caching

        set_cache_backend(None)

    @pytest.mark.asyncio
    async def test_swr_with_key_builder(self):
        mem = MemoryCache(default_ttl=300)
        set_cache_backend(mem)

        @stale_while_revalidate(
            prefix="swr-kb", ttl=60, key_builder=lambda n: f"user:{n}"
        )
        async def get_user(name: str) -> dict:
            return {"name": name}

        result = await get_user("alice")
        assert result == {"name": "alice"}

        set_cache_backend(None)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestCacheUtilities:
    def test_format_etag_empty(self):
        assert format_etag("") == ""

    def test_format_etag_already_quoted(self):
        assert format_etag('"abc"') == '"abc"'

    def test_format_etag_unquoted(self):
        assert format_etag("abc") == '"abc"'

    def test_etag_matches_wildcard(self):
        assert etag_matches("abc", "*") is True

    def test_etag_matches_weak(self):
        assert etag_matches("abc", 'W/"abc"') is True

    def test_etag_matches_strong(self):
        assert etag_matches("abc", '"abc"') is True

    def test_etag_matches_no_match(self):
        assert etag_matches("abc", '"def"') is False

    def test_etag_matches_empty(self):
        assert etag_matches("", '"abc"') is False
        assert etag_matches("abc", None) is False
        assert etag_matches("abc", "") is False

    def test_etag_matches_multiple(self):
        assert etag_matches("abc", '"def", "abc", "ghi"') is True

    def test_etag_matches_empty_parts(self):
        assert etag_matches("abc", '"abc", , ') is True

    def test_versioned_key(self):
        set_cache_key_version(5)
        assert versioned_key("test") == "v5:test"
        set_cache_key_version(1)  # Reset

    def test_get_set_key_version(self):
        original = get_cache_key_version()
        set_cache_key_version(42)
        assert get_cache_key_version() == 42
        set_cache_key_version(original)

    def test_json_default_datetime(self):
        dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC)
        result = _json_default(dt)
        assert "2024-01-15" in result

    def test_json_default_date(self):
        d = date(2024, 1, 15)
        result = _json_default(d)
        assert result == "2024-01-15"

    def test_json_default_time(self):
        t = time(12, 30)
        result = _json_default(t)
        assert "12:30" in result

    def test_json_default_other(self):
        result = _json_default(42)
        assert result == "42"

    def test_normalize_payload(self):
        normalized, serialized = _normalize_payload({"key": "value"})
        assert normalized == {"key": "value"}
        assert isinstance(serialized, bytes)

    @pytest.mark.asyncio
    async def test_get_cache_client_redis(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis
        set_cache_backend(cache)

        client = await get_cache_client()
        assert client is fake_redis

        set_cache_backend(None)
        await cache.close()

    @pytest.mark.asyncio
    async def test_get_cache_client_tiered(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        l2 = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        l2._client = fake_redis
        tiered = TieredCache(MemoryCache(), l2)
        set_cache_backend(tiered)

        client = await get_cache_client()
        assert client is fake_redis

        set_cache_backend(None)
        await l2.close()

    @pytest.mark.asyncio
    async def test_get_cache_client_unsupported(self):
        set_cache_backend(NullCache())

        with pytest.raises(RuntimeError, match="does not support"):
            await get_cache_client()

        set_cache_backend(None)

    @pytest.mark.asyncio
    async def test_shutdown_cache(self):
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        cache._client = fake_redis
        set_cache_backend(cache)

        await shutdown_cache()
        # Backend should be cleared
        from app.deps.cache import _cache_backend

        assert _cache_backend is None

    def test_get_cache_lazy_init(self, monkeypatch):
        """get_cache() creates backend lazily."""
        from app.core.config import settings
        from app.deps import cache as cache_mod

        cache_mod._cache_backend = None
        monkeypatch.setattr(settings, "cache_enabled", False)
        backend = get_cache()
        assert isinstance(backend, NullCache)
        cache_mod._cache_backend = None


# ---------------------------------------------------------------------------
# CacheEntry probabilistic refresh
# ---------------------------------------------------------------------------


class TestCacheEntryRefresh:
    def test_expired_always_refreshes(self):
        entry = CacheEntry(
            etag="x", payload={}, stored_at=time_module.time() - 200, ttl_seconds=100
        )
        assert entry.should_refresh_probabilistic() is True

    def test_zero_ttl_no_refresh(self):
        entry = CacheEntry(
            etag="x", payload={}, stored_at=time_module.time(), ttl_seconds=0
        )
        assert entry.should_refresh_probabilistic() is False

    def test_fresh_entry_usually_no_refresh(self):
        entry = CacheEntry(
            etag="x", payload={}, stored_at=time_module.time(), ttl_seconds=3600
        )
        # With 1 hour TTL and just created, refresh should be unlikely
        # XFetch algorithm uses log(random), so ~37% probability per call
        # We just verify it doesn't ALWAYS refresh (which would indicate a bug)
        refreshes = sum(entry.should_refresh_probabilistic() for _ in range(100))
        assert refreshes < 100  # Not ALL refreshes
