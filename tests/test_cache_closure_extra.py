"""Additional deterministic cache-backend and decorator coverage."""

from __future__ import annotations

import asyncio
import importlib.util
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.deps import cache as cache_module
from app.deps.cache import (
    CacheEntry,
    MemoryCache,
    NatsKVCache,
    RedisCache,
    RedisClusterCache,
    TieredCache,
    cached,
    etag_matches,
    get_cache,
    set_cache_backend,
    shutdown_cache,
    stale_while_revalidate,
)


@pytest.mark.asyncio
async def test_memory_cache_expiry_eviction_and_pattern_invalidation():
    cache = MemoryCache(default_ttl=60)
    cache._max_size = 1
    await cache.set("first", {"value": 1})
    await cache.set("second", {"value": 2})
    assert await cache.get("first") is None
    assert (await cache.get("second")).payload == {"value": 2}

    cache._entries["expired"] = (
        CacheEntry(etag="expired", payload=None, stored_at=0),
        1,
    )
    assert await cache.get("expired") is None

    await cache.set("user:1", {"id": 1})
    await cache.set("user:2", {"id": 2})
    await cache.invalidate()
    await cache.invalidate("missing:*")
    await cache.invalidate("user:*")
    await cache.invalidate("missing:*")
    assert await cache.get("user:1") is None
    assert await cache.get("user:2") is None


def test_cache_entry_zero_random_factor_is_safe():
    entry = CacheEntry(
        etag="etag",
        payload=None,
        stored_at=cache_module.time_module.time(),
        ttl_seconds=60,
    )
    with patch.object(random, "random", return_value=0):
        assert entry.should_refresh_probabilistic() is True


@pytest.mark.asyncio
async def test_redis_cache_client_creation_close_and_missing_etag():
    client = SimpleNamespace(
        get=AsyncMock(return_value=cache_module.orjson.dumps({"payload": {}})),
        close=MagicMock(return_value=asyncio.sleep(0)),
    )
    cache = RedisCache("redis://test", default_ttl=10)

    with patch.object(cache_module.Redis, "from_url", return_value=client) as factory:
        created = await cache._get_client()

    assert created is client
    factory.assert_called_once()
    assert await cache.get("missing-etag") is None
    await cache.close()
    assert cache._client is None

    sync_close_client = SimpleNamespace(close=MagicMock(return_value=None))
    sync_close_cache = RedisCache("redis://test", default_ttl=10)
    sync_close_cache._client = sync_close_client
    await sync_close_cache.close()
    sync_close_client.close.assert_called_once()

    no_close_cache = RedisCache("redis://test", default_ttl=10)
    no_close_cache._client = SimpleNamespace()
    await no_close_cache.close()


@pytest.mark.asyncio
async def test_redis_client_double_checked_lock_and_scan_error_paths():
    client = SimpleNamespace(
        scan=AsyncMock(side_effect=[(1, []), (0, [])]),
        delete=AsyncMock(),
    )
    cache = RedisCache("redis://test", default_ttl=10)
    with patch.object(cache_module.Redis, "from_url", return_value=client):
        await cache._client_lock.acquire()
        first_task = asyncio.create_task(cache._get_client())
        await asyncio.sleep(0)
        second_task = asyncio.create_task(cache._get_client())
        await asyncio.sleep(0)
        cache._client_lock.release()
        first, second = await asyncio.gather(first_task, second_task)
    assert first is client
    assert second is client

    await cache.invalidate("pattern:*")
    assert client.scan.await_count == 2

    client.scan.side_effect = cache_module.RedisError("offline")
    await cache.invalidate("pattern:*")


@pytest.mark.asyncio
async def test_redis_cache_pattern_scan_without_matches():
    client = SimpleNamespace(
        scan=AsyncMock(return_value=(0, [])),
        delete=AsyncMock(),
    )
    cache = RedisCache("redis://test", default_ttl=10)
    cache._client = client

    await cache.invalidate("pattern:*")

    client.scan.assert_awaited_once_with(0, match="pattern:*", count=100)
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cluster_backend_success_and_import_fallback(monkeypatch):
    cluster_client = SimpleNamespace(
        get=AsyncMock(
            return_value=cache_module.orjson.dumps(
                {"etag": "e", "payload": {"ok": True}}
            )
        ),
        set=AsyncMock(),
        delete=AsyncMock(),
        scan=AsyncMock(return_value=(0, [])),
        aclose=AsyncMock(),
    )
    cache = RedisClusterCache("redis://cluster", default_ttl=10)
    with patch(
        "redis.asyncio.cluster.RedisCluster.from_url", return_value=cluster_client
    ):
        await cache._client_lock.acquire()
        first_task = asyncio.create_task(cache._get_client())
        await asyncio.sleep(0)
        second_task = asyncio.create_task(cache._get_client())
        await asyncio.sleep(0)
        cache._client_lock.release()
        first, second = await asyncio.gather(first_task, second_task)
        assert first is cluster_client
        assert second is cluster_client
    assert (await cache.get("key")).payload == {"ok": True}
    await cache.set("key", {"value": 1}, ttl=0)
    await cache.invalidate("key", "pattern:*")
    await cache.close()
    assert cache._client is None

    pattern_client = SimpleNamespace(
        scan=AsyncMock(side_effect=[(1, ["pattern:1"]), (0, [])]),
        delete=AsyncMock(),
    )
    pattern_cache = RedisClusterCache("redis://cluster", default_ttl=10)
    pattern_cache._client = pattern_client
    await pattern_cache.invalidate("pattern:*")
    assert pattern_client.scan.await_count == 2
    pattern_client.delete.assert_awaited_once_with("pattern:1")

    sync_close_client = SimpleNamespace(close=AsyncMock())
    sync_close_cache = RedisClusterCache("redis://cluster", default_ttl=10)
    sync_close_cache._client = sync_close_client
    await sync_close_cache.close()
    sync_close_client.close.assert_awaited_once()

    no_close_cache = RedisClusterCache("redis://cluster", default_ttl=10)
    no_close_cache._client = SimpleNamespace()
    await no_close_cache.close()

    fallback = SimpleNamespace()
    fallback_cache = RedisClusterCache("redis://single", default_ttl=10)
    with (
        patch.dict("sys.modules", {"redis.asyncio.cluster": None}),
        patch.object(cache_module.Redis, "from_url", return_value=fallback),
    ):
        assert await fallback_cache._get_client() is fallback


@pytest.mark.asyncio
async def test_nats_kv_cache_roundtrip_pattern_and_error_paths():
    values: dict[str, bytes] = {}

    class FakeKV:
        async def get(self, key):
            value = values.get(key)
            return SimpleNamespace(value=value) if value is not None else None

        async def put(self, key, value):
            values[key] = value

        async def keys(self):
            return list(values)

        async def delete(self, key):
            values.pop(key, None)

    kv = FakeKV()
    broker = SimpleNamespace(
        is_connected=False,
        js=SimpleNamespace(key_value=AsyncMock(return_value=kv)),
        connect=AsyncMock(),
    )
    cache = NatsKVCache("bucket", default_ttl=15)
    with patch("app.core.nats_broker.broker", broker):
        entry = await cache.set("user:1", {"name": "Ada"})
        loaded = await cache.get("user:1")
        assert loaded.payload == {"name": "Ada"}
        assert entry.ttl_seconds == 15
        assert await cache.get("missing") is None
        await cache.invalidate("user:*")
        assert values == {}
        await cache.close()

    broker.js.key_value.side_effect = RuntimeError("jetstream unavailable")
    failing_cache = NatsKVCache("bucket", default_ttl=0)
    with patch("app.core.nats_broker.broker", broker):
        assert await failing_cache.get("key") is None


@pytest.mark.asyncio
async def test_nats_kv_dcl_connected_and_jetstream_not_ready():
    kv = SimpleNamespace()

    async def key_value(*, bucket):
        assert bucket == "bucket"
        await asyncio.sleep(0)
        return kv

    broker = SimpleNamespace(
        is_connected=True,
        js=SimpleNamespace(key_value=key_value),
        connect=AsyncMock(),
    )
    cache = NatsKVCache("bucket", default_ttl=15)
    with patch("app.core.nats_broker.broker", broker):
        first, second = await asyncio.gather(cache._get_kv(), cache._get_kv())
    assert first is kv
    assert second is kv
    broker.connect.assert_not_awaited()

    none_broker = SimpleNamespace(
        is_connected=True,
        js=None,
        connect=AsyncMock(),
    )
    with patch("app.core.nats_broker.broker", none_broker):
        with pytest.raises(RuntimeError, match="JetStream"):
            await NatsKVCache("bucket", default_ttl=15)._get_kv()


@pytest.mark.asyncio
async def test_nats_kv_cache_write_and_invalidation_fail_closed():
    kv = SimpleNamespace(
        put=AsyncMock(side_effect=ConnectionError("offline")),
        delete=AsyncMock(side_effect=OSError("offline")),
        keys=AsyncMock(return_value=["user:1"]),
    )
    cache = NatsKVCache("bucket", default_ttl=0)
    cache._kv = kv

    entry = await cache.set("key", {"value": 1})
    assert entry.payload == {"value": 1}
    await cache.invalidate("key", "user:*")

    pattern_kv = SimpleNamespace(
        keys=AsyncMock(return_value=["other:1", "user:1", "user:2"]),
        delete=AsyncMock(),
    )
    pattern_cache = NatsKVCache("bucket", default_ttl=15)
    pattern_cache._kv = pattern_kv
    await pattern_cache.invalidate("")
    await pattern_cache.invalidate("user:*")
    assert [call.args[0] for call in pattern_kv.delete.await_args_list] == [
        "user:1",
        "user:2",
    ]
    assert pattern_cache._resolve_ttl(None) == 15
    assert pattern_cache._resolve_ttl(0) == 0


@pytest.mark.asyncio
async def test_cached_decorator_bound_method_and_tiered_l1_ttl():
    cache = MemoryCache(default_ttl=60)
    set_cache_backend(cache)
    calls = 0

    class Service:
        @cached(prefix="bound")
        async def load(self, value: str) -> str:
            nonlocal calls
            calls += 1
            return value

    service = Service()
    assert await service.load("value") == "value"
    assert await service.load("value") == "value"
    assert calls == 1

    l1 = MemoryCache(default_ttl=60)
    l2 = MemoryCache(default_ttl=60)
    tiered = TieredCache(l1, l2)
    set_cache_backend(tiered)

    @cached(prefix="l1", ttl=10, _l1_ttl=2)
    async def compute() -> dict[str, bool]:
        return {"ok": True}

    assert await compute() == {"ok": True}
    assert (await l1.get("l1:")).ttl_seconds == 2
    assert (await l2.get("l1:")).ttl_seconds == 10
    assert (await tiered.get("l1:")).payload == {"ok": True}

    set_cache_backend(None)


@pytest.mark.asyncio
async def test_stale_while_revalidate_refreshes_in_background():
    cache = MemoryCache(default_ttl=120)
    set_cache_backend(cache)
    await cache.set("swr:", {"version": 1})
    entry = cache._entries["swr:"][0]
    entry.stored_at -= 10
    calls = 0

    @stale_while_revalidate(prefix="swr", ttl=1, stale_ttl=30)
    async def load() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"version": 2}

    assert await load() == {"version": 1}
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert calls == 1
    assert (await cache.get("swr:")).payload == {"version": 2}
    set_cache_backend(None)

    fresh_cache = MemoryCache(default_ttl=120)
    set_cache_backend(fresh_cache)
    await fresh_cache.set("fresh:", {"version": 3})

    @stale_while_revalidate(prefix="fresh", ttl=60, stale_ttl=30)
    async def load_fresh() -> dict[str, int]:
        return {"version": 4}

    assert await load_fresh() == {"version": 3}
    set_cache_backend(None)


def test_cache_module_orjson_compatibility_fallback():
    module_name = "app.deps.cache_fallback_coverage"
    module_path = cache_module.__file__
    assert module_path is not None
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    fallback_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = fallback_module
    original_import = __import__

    def blocked_import(name, *args, **kwargs):
        if name == "orjson":
            raise ImportError("orjson intentionally unavailable")
        return original_import(name, *args, **kwargs)

    try:
        with patch("builtins.__import__", side_effect=blocked_import):
            assert spec.loader is not None
            spec.loader.exec_module(fallback_module)
        encoded = fallback_module.orjson.dumps({"b": 2, "a": 1})
        assert fallback_module.orjson.loads(encoded)["a"] == 1
    finally:
        sys.modules.pop(module_name, None)


def test_cache_backend_factories_and_etag_edges(monkeypatch):
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "cache_backend_normalized", "nats")
    monkeypatch.setattr(settings, "cache_nats_bucket", "test-bucket")
    backend = cache_module.create_cache_backend()
    assert isinstance(backend, NatsKVCache)

    set_cache_backend(None)
    with patch.object(
        cache_module, "create_cache_backend", return_value=backend
    ) as factory:
        assert get_cache() is backend
        assert get_cache() is backend
    factory.assert_called_once()
    set_cache_backend(None)

    factory_started = Event()
    release_factory = Event()

    def slow_factory():
        factory_started.set()
        assert release_factory.wait(timeout=1)
        return backend

    with patch.object(
        cache_module, "create_cache_backend", side_effect=slow_factory
    ) as factory:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(get_cache) for _item in range(2)]
            assert factory_started.wait(timeout=1)
            release_factory.set()
            results = [future.result(timeout=1) for future in futures]
    assert results == [backend, backend]
    factory.assert_called_once()
    set_cache_backend(None)

    assert etag_matches("etag", ", ,") is False
    assert etag_matches("etag", "etag") is True


@pytest.mark.asyncio
async def test_shutdown_cache_handles_empty_backend():
    set_cache_backend(None)
    await shutdown_cache()

    backend = SimpleNamespace(
        close=AsyncMock(),
        l2=SimpleNamespace(close=AsyncMock()),
    )
    set_cache_backend(backend)
    await shutdown_cache()
    backend.close.assert_awaited_once()
    backend.l2.close.assert_awaited_once()

    backend_without_close = SimpleNamespace(l2=SimpleNamespace(close=AsyncMock()))
    set_cache_backend(backend_without_close)
    await shutdown_cache()
    backend_without_close.l2.close.assert_awaited_once()
