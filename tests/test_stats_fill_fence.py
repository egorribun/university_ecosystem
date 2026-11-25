from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fakeredis import FakeServer
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError, WatchError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.deps.cache import (
    MemoryCache,
    NatsKVCache,
    NullCache,
    RedisCache,
    RedisClusterCache,
    TieredCache,
    cache_payload_etag,
)
from app.services.stats_cache import get_cached_stats
from app.services.stats_fill_fence import StatsFillFence

KEY = "stats:grades:7:90d"
A, B = "a" * 32, "b" * 32


@pytest_asyncio.fixture(params=["memory", "redis"])
async def backend(request):
    if request.param == "memory":
        cache = MemoryCache(default_ttl=120)
        yield cache, None
    else:
        server = FakeServer()
        client = FakeRedis(server=server, decode_responses=True)
        cache = RedisCache(url="unused", default_ttl=120)
        cache._client = client
        yield cache, client
        await client.aclose()


@pytest.mark.asyncio
async def test_legacy_reader_and_writer_accept_the_same_entry_layout(backend):
    cache, client = backend
    fence = StatsFillFence(cache)
    assert await fence.reserve(KEY, A, 10) is True
    entry = await cache.get(KEY)
    assert entry is not None and entry.payload == "~stats-fill-v1:" + A
    assert entry.etag == cache_payload_etag(entry.payload)
    assert 0 < entry.ttl_seconds <= 10
    assert (
        await get_cached_stats(cache=cache, kind="grades", user_id=7, period_key="90d")
        is None
    )
    if client is not None:
        assert await client.exists(KEY) == 1
        assert 0 < await client.pttl(KEY) <= 10_000
    assert await fence.complete(KEY, A, {"value": 4}, 120) is True
    current = await cache.get(KEY)
    assert current is not None and current.payload == {"value": 4}
    assert current.etag == cache_payload_etag({"value": 4})
    assert current.ttl_seconds == 120
    assert await fence.complete(KEY, A, {"value": 5}, 120) is False


@pytest.mark.asyncio
async def test_collision_and_wrong_owner_never_replace_marker(backend):
    cache, _ = backend
    f = StatsFillFence(cache)
    assert await f.reserve(KEY, A, 10) is True
    assert await f.reserve(KEY, B, 10) is False
    assert await f.complete(KEY, B, {"value": 2}, 120) is False
    assert (await cache.get(KEY)).payload == "~stats-fill-v1:" + A


@pytest.mark.asyncio
@pytest.mark.parametrize("old_operation", ["delete", "set"])
async def test_legacy_invalidation_and_set_revoke_old_reservation(
    backend, old_operation
):
    cache, _ = backend
    f = StatsFillFence(cache)
    assert await f.reserve(KEY, A, 10) is True
    if old_operation == "delete":
        await cache.invalidate(KEY)
    else:
        await cache.set(KEY, {"fresh": True}, ttl=120)
    assert await f.complete(KEY, A, {"stale": True}, 120) is False
    entry = await cache.get(KEY)
    assert (
        entry is None if old_operation == "delete" else entry.payload == {"fresh": True}
    )


@pytest.mark.asyncio
async def test_expired_marker_and_new_owner_reject_old_completion(backend):
    cache, client = backend
    f = StatsFillFence(cache)
    assert await f.reserve(KEY, A, 1) is True
    if client is None:
        entry, _ = cache._entries[KEY]
        cache._entries[KEY] = (entry, time.time() - 1)
    else:
        assert await client.expire(KEY, 0)
    assert await f.complete(KEY, A, {"old": True}, 120) is False
    assert await f.reserve(KEY, B, 10) is True
    assert await f.complete(KEY, A, {"old": True}, 120) is False
    assert await f.complete(KEY, B, {"new": True}, 120) is True
    assert (await cache.get(KEY)).payload == {"new": True}


@pytest.mark.asyncio
async def test_competing_reservations_have_one_winner(backend):
    cache, _ = backend
    f = StatsFillFence(cache)
    results = await asyncio.gather(f.reserve(KEY, A, 10), f.reserve(KEY, B, 10))
    assert sorted(results) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "a" * 31, "A" * 32, "g" * 32, "a" * 33])
async def test_invalid_token_cannot_reserve_or_complete(backend, bad):
    cache, _ = backend
    f = StatsFillFence(cache)
    assert await f.reserve(KEY, bad, 10) is None
    assert await f.complete(KEY, bad, {"x": 1}, 10) is None
    assert await cache.get(KEY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, -1, 31, True, 1.5])
async def test_invalid_reservation_ttl_never_creates_marker(backend, ttl):
    cache, _ = backend
    assert await StatsFillFence(cache).reserve(KEY, A, ttl) is None
    assert await cache.get(KEY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["delete", "set", "expire"])
async def test_watch_conflicts_do_not_publish_after_legacy_change(change):
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    try:
        f = StatsFillFence(cache)
        assert await f.reserve(KEY, A, 10) is True
        pipeline = client.pipeline(transaction=True)
        execute = pipeline.execute

        async def interleaved_execute(*args, **kwargs):
            if change == "delete":
                await cache.invalidate(KEY)
            elif change == "set":
                await cache.set(KEY, {"fresh": True}, ttl=120)
            else:
                await client.expire(KEY, 0)
            return await execute(*args, **kwargs)

        with (
            patch.object(pipeline, "execute", side_effect=interleaved_execute),
            patch.object(client, "pipeline", return_value=pipeline),
        ):
            assert await f.complete(KEY, A, {"stale": True}, 120) is False
        entry = await cache.get(KEY)
        assert (
            entry is None
            if change in ("delete", "expire")
            else entry.payload == {"fresh": True}
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redis_response_loss_is_unknown_even_after_successful_exec():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    try:
        f = StatsFillFence(cache)
        assert await f.reserve(KEY, A, 10) is True
        pipeline = client.pipeline(transaction=True)
        execute = pipeline.execute

        async def lost_response(*args, **kwargs):
            await execute(*args, **kwargs)
            raise RedisConnectionError("synthetic")

        with (
            patch.object(pipeline, "execute", side_effect=lost_response),
            patch.object(client, "pipeline", return_value=pipeline),
        ):
            assert await f.complete(KEY, A, {"valid": True}, 120) is None
        assert (await cache.get(KEY)).payload == {"valid": True}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unsupported_backends_fail_closed():
    for cache in (
        NullCache(),
        TieredCache(MemoryCache(), MemoryCache()),
        RedisClusterCache("unused", 120),
        NatsKVCache(bucket="ue_cache", default_ttl=120),
    ):
        f = StatsFillFence(cache)
        assert f.supported is False
        assert await f.reserve(KEY, A, 10) is None
        assert await f.complete(KEY, A, {"x": 1}, 10) is None


@pytest.mark.asyncio
async def test_two_independent_redis_clients_share_one_reservation_key():
    server = FakeServer()
    client1 = FakeRedis(server=server, decode_responses=True)
    client2 = FakeRedis(server=server, decode_responses=True)
    cache1, cache2 = RedisCache("unused", 120), RedisCache("unused", 120)
    cache1._client, cache2._client = client1, client2
    try:
        first, second = StatsFillFence(cache1), StatsFillFence(cache2)
        assert await first.reserve(KEY, A, 10) is True
        assert await second.reserve(KEY, B, 10) is False
        await cache2.invalidate(KEY)
        assert await first.complete(KEY, A, {"stale": True}, 120) is False
        assert await second.reserve(KEY, B, 10) is True
        await cache1.set(KEY, {"fresh": True}, ttl=120)
        assert await second.complete(KEY, B, {"stale": True}, 120) is False
        assert (await cache2.get(KEY)).payload == {"fresh": True}
    finally:
        await client1.aclose()
        await client2.aclose()


@pytest.mark.asyncio
async def test_redis_reserve_response_loss_is_outcome_unknown():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    try:
        f = StatsFillFence(cache)
        original = client.set

        async def response_lost(*args, **kwargs):
            await original(*args, **kwargs)
            raise RedisConnectionError("synthetic")

        with patch.object(client, "set", side_effect=response_lost):
            assert await f.reserve(KEY, A, 10) is None
        assert (await cache.get(KEY)).payload == "~stats-fill-v1:" + A
        assert await f.reserve(KEY, B, 10) is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redis_error_before_exec_reports_unavailable_without_legacy_fallback():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    try:
        f = StatsFillFence(cache)
        assert await f.reserve(KEY, A, 10) is True
        with patch.object(
            client, "pipeline", side_effect=RedisConnectionError("synthetic")
        ):
            assert await f.complete(KEY, A, {"x": 1}, 120) is None
        assert (await cache.get(KEY)).payload == "~stats-fill-v1:" + A
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_corrupt_or_ordinary_entry_is_not_overwritten_by_completion():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    try:
        f = StatsFillFence(cache)
        for raw in ("{", "[]", "{}"):
            await client.set(KEY, raw, ex=10)
            assert await f.reserve(KEY, A, 10) is False
            assert await f.complete(KEY, A, {"x": 1}, 120) is False
            assert await client.get(KEY) == raw
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_explicitly_reusing_a_token_cannot_be_distinguished_after_delete():
    cache = MemoryCache()
    f = StatsFillFence(cache)
    assert await f.reserve(KEY, A, 10) is True
    await cache.invalidate(KEY)
    assert await f.reserve(KEY, A, 10) is True
    # A stale caller holding an identical token is indistinguishable: callers
    # must mint a fresh cryptographically random token for every attempt.
    assert await f.complete(KEY, A, {"old": True}, 120) is True


@pytest.mark.asyncio
async def test_memory_subclass_is_not_assumed_synchronous():
    class CustomMemory(MemoryCache):
        pass

    f = StatsFillFence(CustomMemory())
    assert f.supported is False
    assert await f.reserve(KEY, A, 10) is None
    assert await f.complete(KEY, A, {"x": 1}, 120) is None


@pytest.mark.asyncio
async def test_tiered_fence_uses_authoritative_l2_and_normal_l1_readthrough():
    client = FakeRedis(decode_responses=True)
    redis_cache = RedisCache("unused", 120)
    redis_cache._client = client
    l1 = MemoryCache(default_ttl=60)
    cache = TieredCache(l1, redis_cache)
    fence = StatsFillFence(cache)
    try:
        assert fence.supported is True
        assert await fence.reserve(KEY, A, 10) is True
        assert await l1.get(KEY) is None
        assert await fence.complete(KEY, A, {"value": 4}, 120) is True
        assert await l1.get(KEY) is None
        assert (await cache.get(KEY)).payload == {"value": 4}
        assert (await l1.get(KEY)).payload == {"value": 4}
        await cache.invalidate(KEY)
        assert await fence.reserve(KEY, B, 10) is True
        await cache.invalidate(KEY)
        assert await fence.complete(KEY, B, {"stale": True}, 120) is False
        assert await cache.get(KEY) is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_tiered_marker_is_not_promoted_by_two_independent_workers():
    server = FakeServer()
    clients = [FakeRedis(server=server, decode_responses=True) for _ in range(2)]
    l2s = [RedisCache("unused", 120) for _ in clients]
    for redis_cache, client in zip(l2s, clients, strict=True):
        redis_cache._client = client
    l1s = [MemoryCache(default_ttl=60) for _ in clients]
    caches = [TieredCache(l1, l2) for l1, l2 in zip(l1s, l2s, strict=True)]
    fence = StatsFillFence(caches[0])
    try:
        assert await fence.reserve(KEY, A, 10) is True
        assert 0 < await clients[0].pttl(KEY) <= 10_000
        assert (await l2s[0].get(KEY)).payload == "~stats-fill-v1:" + A
        for cache, l1 in zip(caches, l1s, strict=True):
            assert (
                await get_cached_stats(
                    cache=cache, kind="grades", user_id=7, period_key="90d"
                )
                is None
            )
            assert await l1.get(KEY) is None
        assert await fence.complete(KEY, A, {"value": 4}, 120) is True
        for cache, l1 in zip(caches, l1s, strict=True):
            assert (
                await get_cached_stats(
                    cache=cache, kind="grades", user_id=7, period_key="90d"
                )
            ).payload == {"value": 4}
            assert (await l1.get(KEY)).payload == {"value": 4}
    finally:
        for client in clients:
            await client.aclose()


@pytest.mark.asyncio
async def test_legacy_best_effort_delete_failure_is_not_covered_by_fence():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    fence = StatsFillFence(cache)
    try:
        assert await fence.reserve(KEY, A, 10) is True
        with patch.object(
            client, "delete", side_effect=RedisConnectionError("synthetic")
        ):
            await cache.invalidate(KEY)
        assert await fence.complete(KEY, A, {"old": True}, 120) is True
        assert (await cache.get(KEY)).payload == {"old": True}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_old_unconditional_writer_remains_outside_fence_guarantee():
    cache = MemoryCache(default_ttl=120)
    fence = StatsFillFence(cache)
    assert await fence.reserve(KEY, A, 10) is True
    await cache.invalidate(KEY)
    await cache.set(KEY, {"old_writer": "stale"}, ttl=120)
    assert await fence.complete(KEY, A, {"new_fence": "stale"}, 120) is False
    assert (await cache.get(KEY)).payload == {"old_writer": "stale"}


@pytest.mark.asyncio
async def test_memory_does_not_complete_nonexpiring_marker_and_reclaims_expired():
    cache = MemoryCache()
    fence = StatsFillFence(cache)
    assert await fence.reserve(KEY, A, 10) is True
    marker, _ = cache._entries[KEY]
    cache._entries[KEY] = (marker, 0)
    assert await fence.complete(KEY, A, {"stale": True}, 120) is False
    cache._entries[KEY] = (marker, time.time() - 1)
    assert await fence.reserve(KEY, B, 10) is True
    assert await fence.complete(KEY, B, {"fresh": True}, 120) is True


@pytest.mark.asyncio
async def test_redis_does_not_complete_marker_without_expiry():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    fence = StatsFillFence(cache)
    try:
        assert await fence.reserve(KEY, A, 10) is True
        assert await client.persist(KEY)
        assert await fence.complete(KEY, A, {"stale": True}, 120) is False
        assert (await cache.get(KEY)).payload == "~stats-fill-v1:" + A
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unexpected_serialization_error_propagates():
    cache = MemoryCache()
    fence = StatsFillFence(cache)
    assert await fence.reserve(KEY, A, 10) is True
    with (
        patch(
            "app.services.stats_fill_fence._normalize_payload",
            side_effect=TypeError("synthetic"),
        ),
        pytest.raises(TypeError),
    ):
        await fence.complete(KEY, A, {"x": object()}, 120)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_type", [RedisConnectionError, RedisTimeoutError, OSError, TimeoutError]
)
@pytest.mark.parametrize("linkage", ["cause", "context", "nested"])
async def test_transport_chained_watcherror_after_commit_is_unknown(
    failure_type, linkage
):
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    fence = StatsFillFence(cache)
    try:
        assert await fence.reserve(KEY, A, 10) is True
        pipeline = client.pipeline(transaction=True)
        execute = pipeline.execute

        def raise_implicit_watcherror():
            raise WatchError("synthetic")

        async def committed_then_response_lost(*args, **kwargs):
            await execute(*args, **kwargs)
            try:
                raise failure_type("synthetic")
            except failure_type as transport:
                if linkage == "cause":
                    raise WatchError("synthetic") from transport
                if linkage == "context":
                    raise_implicit_watcherror()
                try:
                    raise RuntimeError("wrapper") from transport
                except RuntimeError as wrapper:
                    raise WatchError("synthetic") from wrapper

        with (
            patch.object(pipeline, "execute", side_effect=committed_then_response_lost),
            patch.object(client, "pipeline", return_value=pipeline),
            patch("app.services.stats_fill_fence.record_redis_command") as record,
            patch("app.services.stats_fill_fence.logger.warning") as warning,
        ):
            assert await fence.complete(KEY, A, {"committed": True}, 120) is None
        assert (await cache.get(KEY)).payload == {"committed": True}
        assert record.call_args.kwargs["success"] is False
        assert warning.call_args.kwargs["error_type"] == failure_type.__name__
        assert KEY not in str(warning.call_args)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("linkage", ["suppressed", "non_transport", "cycle"])
async def test_nontransport_or_suppressed_context_remains_contention(linkage):
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    fence = StatsFillFence(cache)
    try:
        assert await fence.reserve(KEY, A, 10) is True
        pipeline = client.pipeline(transaction=True)

        async def invalidated_then_conflict(*_args, **_kwargs):
            await cache.invalidate(KEY)
            if linkage == "suppressed":
                try:
                    raise RedisConnectionError("unrelated")
                except RedisConnectionError:
                    raise WatchError("contended") from None
            if linkage == "non_transport":
                raise WatchError("contended") from ResponseError("synthetic")
            cyclic = RuntimeError("synthetic")
            cyclic.__cause__ = cyclic
            raise WatchError("contended") from cyclic

        with (
            patch.object(pipeline, "execute", side_effect=invalidated_then_conflict),
            patch.object(client, "pipeline", return_value=pipeline),
            patch("app.services.stats_fill_fence.record_redis_command") as record,
            patch("app.services.stats_fill_fence.logger.warning") as warning,
        ):
            assert await fence.complete(KEY, A, {"stale": True}, 120) is False
        assert record.call_args.kwargs["success"] is True
        warning.assert_not_called()
        assert await cache.get(KEY) is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redis_disconnect_callback_after_commit_preserves_unknown():
    client = FakeRedis(decode_responses=True)
    cache = RedisCache("unused", 120)
    cache._client = client
    fence = StatsFillFence(cache)
    offline_client = Redis(host="127.0.0.1", port=1)
    redis_pipeline = offline_client.pipeline(transaction=True)
    redis_pipeline.watching = True
    connection = type("OfflineConnection", (), {"disconnect": AsyncMock()})()
    try:
        assert await fence.reserve(KEY, A, 10) is True
        fake_pipeline = client.pipeline(transaction=True)
        execute = fake_pipeline.execute

        async def committed_then_disconnect(*args, **kwargs):
            await execute(*args, **kwargs)
            try:
                raise RedisConnectionError("synthetic")
            except RedisConnectionError as transport:
                await redis_pipeline._disconnect_reset_raise_on_watching(
                    connection, transport
                )

        with (
            patch.object(
                fake_pipeline, "execute", side_effect=committed_then_disconnect
            ),
            patch.object(client, "pipeline", return_value=fake_pipeline),
        ):
            assert await fence.complete(KEY, A, {"committed": True}, 120) is None
        connection.disconnect.assert_awaited_once()
        assert (await cache.get(KEY)).payload == {"committed": True}
    finally:
        await client.aclose()
        await offline_client.aclose()
