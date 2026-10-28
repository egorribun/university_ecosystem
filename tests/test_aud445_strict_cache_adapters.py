"""Strict invalidation must report cache transport failures to the outbox."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from nats.js.errors import KeyNotFoundError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import nats_broker
from app.deps import cache as cache_module


@pytest.mark.asyncio
async def test_redis_strict_invalidation_reports_failure_and_retries_exact_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = cache_module.RedisCache("redis://localhost:6379/0", default_ttl=60)
    cache._client = client
    await client.set("v1:chat:a:participants", "old")
    await client.set("v1:user:a:presence_audience", "old")
    real_delete = client.delete
    attempts = 0

    async def fail_second(*keys: str) -> int:
        nonlocal attempts
        assert len(keys) == 1
        attempts += 1
        if attempts == 2:
            raise RedisConnectionError("owned transport fault")
        return await real_delete(*keys)

    monkeypatch.setattr(client, "delete", fail_second)
    try:
        assert hasattr(cache, "invalidate_strict")
        with pytest.raises(cache_module.StrictCacheInvalidationError):
            await cache.invalidate_strict(
                "v1:chat:a:participants", "v1:user:a:presence_audience"
            )
        assert await client.get("v1:chat:a:participants") is None
        assert await client.get("v1:user:a:presence_audience") == "old"

        monkeypatch.setattr(client, "delete", real_delete)
        assert (
            await cache.invalidate_strict(
                "v1:chat:a:participants", "v1:user:a:presence_audience"
            )
            == "shared"
        )
        assert await client.get("v1:user:a:presence_audience") is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cluster_invalidation_never_combines_different_hash_slots() -> None:
    cache = cache_module.RedisClusterCache("redis://localhost:6379/0", default_ttl=60)
    client = SimpleNamespace(delete=AsyncMock(return_value=1))
    cache._client = client
    assert hasattr(cache, "invalidate_strict")

    assert (
        await cache.invalidate_strict(
            "v1:chat:a:participants", "v1:user:b:presence_audience"
        )
        == "shared"
    )
    assert [args.args for args in client.delete.await_args_list] == [
        ("v1:chat:a:participants",),
        ("v1:user:b:presence_audience",),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_key", ["v1:user:*", "v1:user:?", "v1:user:[ab]"])
async def test_strict_invalidation_rejects_patterns_before_any_deletion(
    bad_key: str,
) -> None:
    cache = cache_module.RedisCache("redis://localhost:6379/0", default_ttl=60)
    client = SimpleNamespace(delete=AsyncMock(return_value=1))
    cache._client = client
    assert hasattr(cache, "invalidate_strict")

    with pytest.raises(ValueError):
        await cache.invalidate_strict("v1:user:valid", bad_key)
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_nats_missing_key_is_idempotent_but_transport_failure_is_visible() -> (
    None
):
    cache = cache_module.NatsKVCache(bucket="aud445", default_ttl=60)
    kv = SimpleNamespace(
        delete=AsyncMock(side_effect=[KeyNotFoundError(), OSError("owned outage")])
    )
    cache._kv = kv
    assert hasattr(cache, "invalidate_strict")

    assert await cache.invalidate_strict("v1:user:missing") == "shared"
    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:unavailable")


@pytest.mark.asyncio
async def test_uninitialized_nats_is_a_retryable_strict_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        nats_broker, "broker", SimpleNamespace(is_connected=True, js=None)
    )
    cache = cache_module.NatsKVCache(bucket="aud445", default_ttl=60)

    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:a")


@pytest.mark.asyncio
async def test_tiered_strict_invalidation_clears_local_layer_even_if_shared_fails() -> (
    None
):
    local = cache_module.MemoryCache(default_ttl=60)
    await local.set("v1:user:a", "stale")
    shared = cache_module.RedisCache("redis://localhost:6379/0", default_ttl=60)
    shared._client = SimpleNamespace(
        delete=AsyncMock(side_effect=RedisConnectionError("outage"))
    )
    cache = cache_module.TieredCache(local, shared)
    assert hasattr(cache, "invalidate_strict")

    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:a")
    assert await local.get("v1:user:a") is None


@pytest.mark.asyncio
async def test_strict_null_and_memory_scope_are_not_reported_as_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = cache_module.MemoryCache(default_ttl=60)
    await memory.set("v1:user:a", "old")
    assert hasattr(memory, "invalidate_strict")
    assert await memory.invalidate_strict("v1:user:a") == "process_only"
    assert await memory.get("v1:user:a") is None

    null = cache_module.NullCache()
    monkeypatch.setattr(cache_module, "settings", SimpleNamespace(cache_enabled=False))
    assert await null.invalidate_strict("v1:user:a") == "disabled"
    monkeypatch.setattr(cache_module, "settings", SimpleNamespace(cache_enabled=True))
    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await null.invalidate_strict("v1:user:a")


@pytest.mark.asyncio
async def test_tiered_backend_without_shared_url_cannot_acknowledge_strict_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cache_module,
        "settings",
        SimpleNamespace(
            cache_enabled=True,
            cache_backend_normalized="tiered",
            cache_default_ttl_seconds=60,
            cache_l1_ttl_seconds=60,
            cache_redis_url=None,
        ),
    )
    cache = cache_module.create_cache_backend()
    await cache.set("v1:user:a", "stale")

    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:a")
    assert await cache.get("v1:user:a") is None


@pytest.mark.asyncio
async def test_unimplemented_adapter_cannot_report_cleanup_success() -> None:
    cache = cache_module.BaseCache()
    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:a")


@pytest.mark.asyncio
async def test_empty_shared_invalidation_does_not_connect() -> None:
    redis = cache_module.RedisCache("redis://localhost:6379/0", default_ttl=60)
    cluster = cache_module.RedisClusterCache("redis://localhost:6379/0", default_ttl=60)
    nats = cache_module.NatsKVCache(bucket="aud445", default_ttl=60)
    for backend in (redis, cluster, nats):
        assert await backend.invalidate_strict() == "shared"
        assert getattr(backend, "_client", None) is None


@pytest.mark.asyncio
async def test_cluster_transport_failure_is_a_retryable_strict_failure() -> None:
    cluster = cache_module.RedisClusterCache("redis://localhost:6379/0", default_ttl=60)
    cluster._client = SimpleNamespace(
        delete=AsyncMock(side_effect=RedisConnectionError("owned outage"))
    )
    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cluster.invalidate_strict("v1:user:a")


@pytest.mark.asyncio
async def test_tiered_success_scope_reflects_shared_or_local_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = cache_module.RedisCache("redis://localhost:6379/0", default_ttl=60)
    shared._client = SimpleNamespace(delete=AsyncMock(return_value=1))
    local = cache_module.MemoryCache(default_ttl=60)
    assert (
        await cache_module.TieredCache(local, shared).invalidate_strict("v1:user:a")
        == "shared"
    )
    assert (
        await cache_module.TieredCache(local, local).invalidate_strict("v1:user:a")
        == "process_only"
    )
    monkeypatch.setattr(cache_module, "settings", SimpleNamespace(cache_enabled=False))
    null = cache_module.NullCache()
    assert (
        await cache_module.TieredCache(null, null).invalidate_strict("v1:user:a")
        == "disabled"
    )


@pytest.mark.asyncio
async def test_tiered_unknown_layer_outcome_is_not_accepted_as_success() -> None:
    local = cache_module.MemoryCache(default_ttl=60)
    await local.set("v1:user:a", "old")
    unknown = SimpleNamespace(invalidate_strict=AsyncMock(return_value=None))
    cache = cache_module.TieredCache(local, unknown)

    with pytest.raises(cache_module.StrictCacheInvalidationError):
        await cache.invalidate_strict("v1:user:a")
    assert await local.get("v1:user:a") is None
