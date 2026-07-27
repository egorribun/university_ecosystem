"""Behavioral coverage closure for the dependency cache backends."""

from __future__ import annotations

import builtins
import runpy
import sys
from datetime import date, datetime, time, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError


def test_orjson_compatibility_fallback_is_usable() -> None:
    from app.deps import cache

    with patch.dict(sys.modules, {"orjson": None}):
        namespace = runpy.run_path(str(cache.__file__), run_name="cache_without_orjson")
    compat = namespace["orjson"]
    assert compat.OPT_SORT_KEYS == 0
    assert compat.OPT_UTC_Z == 0
    assert compat.loads(compat.dumps({"value": 1})) == {"value": 1}
    assert compat.JSONDecodeError is not None


@pytest.mark.asyncio
async def test_cache_entry_random_zero_and_memory_empty_invalidation() -> None:
    from app.deps.cache import CacheEntry, MemoryCache

    entry = CacheEntry(etag="e", payload={}, stored_at=0.0, ttl_seconds=10.0)
    with (
        patch("app.deps.cache.time_module.time", return_value=1.0),
        patch("random.random", return_value=0.0),
    ):
        assert entry.should_refresh_probabilistic(beta=1.0) is True

    cache = MemoryCache()
    await cache.invalidate()


@pytest.mark.asyncio
async def test_redis_client_double_checked_lock_and_close_awaitable() -> None:
    from app.deps import cache as cache_module
    from app.deps.cache import RedisCache

    redis_cache = RedisCache("redis://localhost", default_ttl=10)
    sentinel = MagicMock(name="redis-client")

    class LockThatInitializesClient:
        async def __aenter__(self):
            redis_cache._client = sentinel
            return self

        async def __aexit__(self, *_args):
            return None

    redis_cache._client_lock = LockThatInitializesClient()
    with patch.object(cache_module.Redis, "from_url") as from_url:
        assert await redis_cache._get_client() is sentinel
    from_url.assert_not_called()

    close_client = MagicMock()
    del close_client.aclose
    close_client.close = AsyncMock()
    redis_cache._client = close_client
    await redis_cache.close()
    close_client.close.assert_awaited_once()

    class SyncCloseClient:
        def close(self):
            return None

    redis_cache._client = SyncCloseClient()
    await redis_cache.close()

    class NoCloseClient:
        pass

    redis_cache._client = NoCloseClient()
    await redis_cache.close()


@pytest.mark.asyncio
async def test_redis_get_invalid_etag_and_scan_empty_then_cursor() -> None:
    import orjson

    from app.deps.cache import RedisCache

    redis_cache = RedisCache("redis://localhost", default_ttl=10)
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(
        return_value=orjson.dumps({"payload": {"missing": "etag"}}).decode()
    )
    redis_cache._client = redis_client
    assert await redis_cache.get("missing-etag") is None

    redis_client.scan = AsyncMock(side_effect=[(5, []), (0, [])])
    redis_client.delete = AsyncMock()
    await redis_cache.invalidate("pattern:*")
    assert redis_client.scan.await_count == 2
    redis_client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_invalidate_swallow_redis_error() -> None:
    from app.deps.cache import RedisCache

    redis_cache = RedisCache("redis://localhost", default_ttl=10)
    redis_client = AsyncMock()
    redis_client.delete.side_effect = RedisError("redis unavailable")
    redis_cache._client = redis_client

    with patch("app.deps.cache.record_redis_command") as record_command:
        await redis_cache.invalidate("cache:key")

    record_command.assert_called_once()
    assert record_command.call_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_redis_cluster_normal_client_cached_and_async_close_fallback() -> None:
    from app.deps.cache import RedisClusterCache

    cluster_class = MagicMock()
    cluster_client = MagicMock()
    cluster_class.from_url.return_value = cluster_client
    cluster_module = ModuleType("redis.asyncio.cluster")
    cluster_module.RedisCluster = cluster_class

    cluster_cache = RedisClusterCache("redis://localhost", default_ttl=10)
    real_import = builtins.__import__

    def import_cluster(name, *args, **kwargs):
        if name == "redis.asyncio.cluster":
            return cluster_module
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=import_cluster):
        assert await cluster_cache._get_client() is cluster_client
    assert await cluster_cache._get_client() is cluster_client
    cluster_class.from_url.assert_called_once_with(
        "redis://localhost", decode_responses=True
    )

    close_client = MagicMock()
    del close_client.aclose
    close_client.close = AsyncMock()
    cluster_cache._client = close_client
    await cluster_cache.close()
    close_client.close.assert_awaited_once()

    class NoCloseClient:
        pass

    cluster_cache._client = NoCloseClient()
    await cluster_cache.close()

    raced_cluster = RedisClusterCache("redis://localhost", default_ttl=10)
    raced_client = MagicMock(name="raced-cluster-client")

    class ClusterLockThatInitializesClient:
        async def __aenter__(self):
            raced_cluster._client = raced_client
            return self

        async def __aexit__(self, *_args):
            return None

    raced_cluster._client_lock = ClusterLockThatInitializesClient()
    assert await raced_cluster._get_client() is raced_client


@pytest.mark.asyncio
async def test_redis_cluster_pattern_scan_empty_then_cursor() -> None:
    from app.deps.cache import RedisClusterCache

    cluster_cache = RedisClusterCache("redis://localhost", default_ttl=10)
    cluster_client = AsyncMock()
    cluster_client.scan = AsyncMock(side_effect=[(3, []), (0, [])])
    cluster_client.delete = AsyncMock()
    cluster_cache._client = cluster_client
    await cluster_cache.invalidate("pattern:*")
    assert cluster_client.scan.await_count == 2
    cluster_client.delete.assert_not_awaited()

    cluster_client.scan = AsyncMock(return_value=(0, ["pattern:key"]))
    await cluster_cache.invalidate("pattern:*")
    cluster_client.delete.assert_awaited_once_with("pattern:key")


@pytest.mark.asyncio
async def test_tiered_cache_l1_hit_l2_backfill_and_miss() -> None:
    from app.deps.cache import CacheEntry, TieredCache

    l1 = AsyncMock()
    l2 = AsyncMock()
    tiered = TieredCache(l1, l2)
    l1_entry = CacheEntry("l1", {"source": 1}, 1.0)
    l1.get.return_value = l1_entry
    assert await tiered.get("key") is l1_entry
    l2.get.assert_not_awaited()

    l1.get.return_value = None
    l2_entry = CacheEntry("l2", {"source": 2}, 1.0)
    l2.get.return_value = l2_entry
    assert await tiered.get("key") is l2_entry
    l1.set.assert_awaited_once_with("key", {"source": 2})

    l2.get.return_value = None
    assert await tiered.get("key") is None


@pytest.mark.asyncio
async def test_nats_kv_lifecycle_get_set_and_invalidate() -> None:
    import orjson

    from app.deps.cache import NatsKVCache

    kv = AsyncMock()
    broker = SimpleNamespace(
        is_connected=False,
        connect=AsyncMock(),
        js=SimpleNamespace(key_value=AsyncMock(return_value=kv)),
    )
    nats_cache = NatsKVCache("closure", default_ttl=30)
    with patch("app.core.nats_broker.broker", broker):
        assert await nats_cache._get_kv() is kv
        assert await nats_cache._get_kv() is kv
    broker.connect.assert_awaited_once()

    kv.get.return_value = SimpleNamespace(
        value=orjson.dumps(
            {
                "etag": "nats-etag",
                "payload": {"value": 1},
                "stored_at": 0,
                "ttl_seconds": 30,
            }
        )
    )
    result = await nats_cache.get("key")
    assert result is not None
    assert result.etag == "nats-etag"
    kv.get.return_value = None
    assert await nats_cache.get("missing") is None

    entry = await nats_cache.set("key", {"value": 2}, ttl=10)
    assert entry.payload == {"value": 2}
    kv.put.assert_awaited_once()

    await nats_cache.invalidate()
    kv.keys.return_value = ["prefix:a", "other"]
    await nats_cache.invalidate("exact", "prefix:*")
    kv.delete.assert_any_await("exact")
    kv.delete.assert_any_await("prefix:a")

    await nats_cache.close()
    assert nats_cache._kv is None
    assert nats_cache._resolve_ttl(None) == 30
    assert nats_cache._resolve_ttl(-1) == 0


@pytest.mark.asyncio
async def test_nats_kv_optional_connection_and_error_paths() -> None:
    from app.deps.cache import NatsKVCache

    nats_cache = NatsKVCache("closure", default_ttl=30)
    broker = SimpleNamespace(
        is_connected=True,
        connect=AsyncMock(),
        js=None,
    )
    with patch("app.core.nats_broker.broker", broker):
        with pytest.raises(RuntimeError, match="JetStream"):
            await nats_cache._get_kv()

    raced_kv = object()
    raced_nats = NatsKVCache("closure", default_ttl=30)

    class NatsLockThatInitializesKV:
        async def __aenter__(self):
            raced_nats._kv = raced_kv
            return self

        async def __aexit__(self, *_args):
            return None

    raced_nats._lock = NatsLockThatInitializesKV()
    assert await raced_nats._get_kv() is raced_kv

    kv = AsyncMock()
    kv.get.side_effect = RuntimeError("read failed")
    kv.put.side_effect = OSError("write failed")
    kv.delete.side_effect = OSError("delete failed")
    nats_cache._kv = kv
    assert await nats_cache.get("key") is None
    entry = await nats_cache.set("key", {"value": 1})
    assert entry.payload == {"value": 1}
    await nats_cache.invalidate("key")


@pytest.mark.asyncio
async def test_cached_decorator_uses_distinct_tiered_l1_ttl() -> None:
    from app.deps.cache import TieredCache, cached

    l1 = AsyncMock()
    l2 = AsyncMock()
    cache = TieredCache(l1, l2)
    cache.get = AsyncMock(return_value=None)

    @cached(
        prefix="closure",
        ttl=timedelta(seconds=20),
        _l1_ttl=timedelta(seconds=3),
    )
    async def load(value: int) -> dict[str, int]:
        return {"value": value}

    with patch("app.deps.cache.get_cache", return_value=cache):
        result = await load(7)
    assert result == {"value": 7}
    l2.set.assert_awaited_once_with("closure:7", result, ttl=20)
    l1.set.assert_awaited_once_with("closure:7", result, ttl=3)


@pytest.mark.asyncio
async def test_cached_decorator_skips_self_in_bound_method_key() -> None:
    from app.deps.cache import cached

    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None

    class Loader:
        @cached(prefix="bound")
        async def load(self, value: int) -> int:
            return value

    with patch("app.deps.cache.get_cache", return_value=cache):
        assert await Loader().load(4) == 4
    cache.set.assert_awaited_once_with("bound:4", 4, ttl=None)


@pytest.mark.asyncio
async def test_stale_while_revalidate_returns_stale_when_already_locked() -> None:
    from app.deps.cache import CacheEntry, stale_while_revalidate

    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = CacheEntry(
        etag="stale", payload={"value": 1}, stored_at=0.0, ttl_seconds=1.0
    )
    fake_task = MagicMock()

    def create_task_without_running(coro):
        coro.close()
        return fake_task

    @stale_while_revalidate(prefix="closure", ttl=1, stale_ttl=10)
    async def load() -> dict[str, int]:
        return {"value": 2}

    with (
        patch("app.deps.cache.get_cache", return_value=cache),
        patch(
            "app.deps.cache.asyncio.create_task",
            side_effect=create_task_without_running,
        ),
    ):
        first = await load()
        second = await load()
    assert first == {"value": 1}
    assert second == {"value": 1}
    fake_task.add_done_callback.assert_called_once()


def test_create_cache_backend_nats_and_get_cache_inner_double_check() -> None:
    from app.deps import cache as cache_module
    from app.deps.cache import NatsKVCache

    settings = SimpleNamespace(
        cache_enabled=True,
        cache_backend_normalized="nats",
        cache_backend="redis",
        cache_default_ttl_seconds=17,
        cache_nats_bucket="closure-bucket",
    )
    with patch.object(cache_module, "settings", settings):
        backend = cache_module.create_cache_backend()
    assert isinstance(backend, NatsKVCache)
    assert backend._bucket_name == "closure-bucket"

    marker = object()
    cache_module.set_cache_backend(None)
    lock = MagicMock()
    lock.__enter__.side_effect = lambda: cache_module.set_cache_backend(marker)
    with (
        patch.object(cache_module, "_cache_backend_lock", lock),
        patch.object(cache_module, "create_cache_backend") as create_backend,
    ):
        assert cache_module.get_cache() is marker
    create_backend.assert_not_called()
    cache_module.set_cache_backend(None)


@pytest.mark.asyncio
async def test_shutdown_cache_handles_none_bare_and_nested_close() -> None:
    from app.deps import cache as cache_module

    cache_module.set_cache_backend(None)
    await cache_module.shutdown_cache()

    class BareBackend:
        pass

    bare = BareBackend()
    cache_module.set_cache_backend(bare)
    await cache_module.shutdown_cache()

    outer_close = AsyncMock()
    inner_close = AsyncMock()
    nested = SimpleNamespace(close=inner_close)
    cache_module.set_cache_backend(SimpleNamespace(close=outer_close, l2=nested))
    await cache_module.shutdown_cache()
    outer_close.assert_awaited_once()
    inner_close.assert_awaited_once()


def test_etag_matches_ignores_empty_header_parts() -> None:
    from app.deps.cache import etag_matches

    assert etag_matches("abc", " , ") is False


def test_cache_json_default_supports_temporal_values() -> None:
    from app.deps.cache import _json_default

    assert _json_default(datetime(2024, 1, 2, 3, 4)) == "2024-01-02T03:04:00"
    assert _json_default(date(2024, 1, 2)) == "2024-01-02"
    assert _json_default(time(3, 4)) == "03:04:00"
    assert _json_default(object())
