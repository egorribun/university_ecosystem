"""Behavioral coverage closure for the dependency cache backends."""

from __future__ import annotations

import builtins
import runpy
import sys
from datetime import timedelta
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
async def test_cached_decorator_includes_receiver_in_bound_method_key() -> None:
    from app.deps.cache import cached

    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None

    class Loader:
        @cached(prefix="bound")
        async def load(self, value: int) -> int:
            return value

    loader = Loader()
    with patch("app.deps.cache.get_cache", return_value=cache):
        assert await loader.load(4) == 4
    cache.set.assert_awaited_once_with(f"bound:{loader}:4", 4, ttl=None)


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("l1_ttl", "fill_at", "expires_at"),
    [
        pytest.param(60, 109.5, 110.0, id="late-subsecond-backfill"),
        pytest.param(2, 101.0, 103.0, id="short-l1-control"),
    ],
)
async def test_tiered_backfill_does_not_extend_source_or_l1_expiry(
    l1_ttl: int,
    fill_at: float,
    expires_at: float,
) -> None:
    from app.deps import cache

    now = 100.0
    l1 = cache.MemoryCache(default_ttl=l1_ttl)
    l2 = cache.MemoryCache(default_ttl=10)
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: now)):
        original = await l2.set("bounded-entry", {"value": "original"})
        now = fill_at
        assert await tiered.get("bounded-entry") is original

        now = expires_at
        assert await l1.get("bounded-entry") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_ttl", "l1_ttl", "fill_at", "returned", "promoted", "expires_at"),
    [
        pytest.param(10, 60, 105.0, True, True, 110.0, id="source-bound"),
        pytest.param(10, 2, 101.0, True, True, 103.0, id="short-l1"),
        pytest.param(10, 0, 105.0, True, True, 110.0, id="unbounded-l1"),
        pytest.param(10, 60, 109.0, True, True, 110.0, id="exact-one-second"),
        pytest.param(10, 60, 109.5, True, False, None, id="subsecond"),
        pytest.param(0, 2, 105.0, True, True, 107.0, id="source-zero"),
        pytest.param(0, 0, 105.0, True, True, None, id="both-zero"),
        pytest.param(10, 60, 110.0, False, False, None, id="exact-expiry"),
        pytest.param(10, 60, 110.1, False, False, None, id="expired"),
        pytest.param(-1, 60, 105.0, False, False, None, id="negative"),
        pytest.param("nan", 60, 105.0, False, False, None, id="nonfinite"),
    ],
)
async def test_tiered_redis_envelope_promotion_preserves_expiry(
    source_ttl: int | str,
    l1_ttl: int,
    fill_at: float,
    returned: bool,
    promoted: bool,
    expires_at: float | None,
) -> None:
    from app.deps import cache

    now = fill_at
    payload = {"value": "original"}
    l1 = cache.MemoryCache(default_ttl=l1_ttl)
    l2 = cache.RedisCache("redis://redis.invalid:6379/0", default_ttl=10)
    client = AsyncMock()
    client.get.return_value = cache.orjson.dumps(
        {
            "etag": "source-etag",
            "payload": payload,
            "stored_at": 100.0,
            "ttl_seconds": source_ttl,
        }
    )
    l2._client = client
    tiered = cache.TieredCache(l1, l2)
    clock = SimpleNamespace(time=lambda: now, perf_counter=lambda: now)

    with (
        patch.object(cache, "time_module", clock),
        patch.object(
            cache.Redis,
            "from_url",
            side_effect=AssertionError("unexpected Redis connection"),
        ) as connect,
    ):
        result = await tiered.get("bounded-entry")
        assert (result is not None) is returned
        if result is not None:
            assert result.payload == payload

        local = await l1.get("bounded-entry")
        assert (local is not None) is promoted
        if local is not None:
            assert local.payload == payload
            assert local.etag == "source-etag"
            assert local.stored_at == 100.0
            assert local.ttl_seconds == float(source_ttl)

        if expires_at is not None:
            now = expires_at - 0.001
            assert await l1.get("bounded-entry") is not None
            now = expires_at
            assert await l1.get("bounded-entry") is None
        elif promoted:
            now = 1000.0
            assert await l1.get("bounded-entry") is not None

    connect.assert_not_called()
    client.get.assert_awaited_once_with("bounded-entry")


@pytest.mark.asyncio
@pytest.mark.parametrize("source_ttl", [0.0, 10.0])
async def test_tiered_non_memory_promotion_requires_unbounded_source(
    source_ttl: float,
) -> None:
    from app.deps import cache

    entry = cache.CacheEntry("source", {"value": 1}, 100.0, source_ttl)
    l1 = AsyncMock()
    l1.get.return_value = None
    l2 = AsyncMock()
    l2.get.return_value = entry
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: 105.0)):
        assert await tiered.get("key") is entry

    if source_ttl:
        l1.set.assert_not_awaited()
    else:
        l1.set.assert_awaited_once_with("key", entry.payload)


@pytest.mark.asyncio
async def test_tiered_rechecks_expiry_after_awaiting_l2() -> None:
    from app.deps import cache

    now = 109.0
    entry = cache.CacheEntry("source", {"value": 1}, 100.0, 10.0)
    l1 = cache.MemoryCache(default_ttl=60)
    l2 = AsyncMock()

    async def read_after_expiry(key: str) -> cache.CacheEntry:
        nonlocal now
        assert key == "key"
        now = 110.0
        return entry

    l2.get.side_effect = read_after_expiry
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: now)):
        assert await tiered.get("key") is None
        assert await l1.get("key") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_at", "ttl"),
    [
        pytest.param(True, 10.0, id="boolean-time"),
        pytest.param("100", 10.0, id="text-time"),
        pytest.param(100.0, True, id="boolean-ttl"),
        pytest.param(100.0, "10", id="text-ttl"),
        pytest.param(float("nan"), 10.0, id="nonfinite-time"),
        pytest.param(1e308, 1e308, id="overflowed-deadline"),
        pytest.param(10**1000, 10.0, id="nonrepresentable-time"),
    ],
)
async def test_tiered_refuses_malformed_source_metadata(stored_at, ttl) -> None:
    from app.deps import cache

    l1 = cache.MemoryCache(default_ttl=60)
    l2 = AsyncMock()
    l2.get.return_value = cache.CacheEntry("source", {"value": 1}, stored_at, ttl)
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: 105.0)):
        assert await tiered.get("key") is None
        assert await l1.get("key") is None


@pytest.mark.asyncio
async def test_tiered_promotion_rechecks_after_normalization() -> None:
    from app.deps import cache

    now = 109.0
    entry = cache.CacheEntry("source", {"value": 1}, 100.0, 10.0)
    l1 = cache.MemoryCache(default_ttl=60)
    l2 = AsyncMock()
    l2.get.return_value = entry
    tiered = cache.TieredCache(l1, l2)
    normalize = cache._normalize_payload

    def normalize_after_expiry(payload):
        nonlocal now
        result = normalize(payload)
        now = 110.0
        return result

    with (
        patch.object(cache, "time_module", SimpleNamespace(time=lambda: now)),
        patch.object(cache, "_normalize_payload", normalize_after_expiry),
    ):
        assert await tiered.get("key") is entry
        assert await l1.get("key") is None


@pytest.mark.asyncio
async def test_tiered_promotion_preserves_lru_and_payload_ownership() -> None:
    from app.deps import cache

    l1 = cache.MemoryCache(default_ttl=60, max_size=10)
    l2 = cache.MemoryCache(default_ttl=10)
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: 100.0)):
        for index in range(10):
            await l1.set(f"existing-{index}", {"index": index})
        assert await l1.get("existing-0") is not None
        original = await l2.set("promoted", {"nested": [1]})
        assert await tiered.get("promoted") is original

        local = await l1.get("promoted")
        assert local is not None
        assert local.payload is not original.payload
        assert local.payload["nested"] is not original.payload["nested"]
        local.payload["nested"].append(2)
        assert original.payload == {"nested": [1]}
        assert await l1.get("existing-1") is None
        assert await l1.get("existing-0") is not None
        assert len(l1._entries) == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("source_ttl", [0.0, 10.0])
async def test_tiered_does_not_bypass_memory_subclass_set(source_ttl: float) -> None:
    from app.deps import cache

    calls: list[str] = []

    class CustomMemoryCache(cache.MemoryCache):
        async def set(self, key, payload, ttl=None):
            calls.append(key)
            return await super().set(key, payload, ttl)

    l1 = CustomMemoryCache(default_ttl=60)
    l2 = AsyncMock()
    entry = cache.CacheEntry("source", {"value": 1}, 100.0, source_ttl)
    l2.get.return_value = entry
    tiered = cache.TieredCache(l1, l2)

    with patch.object(cache, "time_module", SimpleNamespace(time=lambda: 105.0)):
        assert await tiered.get("key") is entry
        if source_ttl:
            assert calls == []
            assert await l1.get("key") is None
        else:
            assert calls == ["key"]
            assert await l1.get("key") is not None
