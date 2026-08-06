import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import REGISTRY

from app.core.spicedb_watch import _invalidate_for_update, _watch_once


def make_mock_update(user_id: str, resource_type: str, resource_id: str):
    mock = AsyncMock()
    mock.relationship.resource.object_type = resource_type
    mock.relationship.resource.object_id = resource_id
    mock.relationship.subject.object.object_id = user_id
    return mock


@pytest.mark.anyio
async def test_concurrent_invalidate_multiple_users_and_resources():
    """Stress test 100 concurrent _invalidate_for_update calls on a 1000-entry cache."""
    cache = {}
    for u in range(50):
        for r in range(20):
            cache[
                (f"user-{u}", "document", f"doc-{r}", "read", "tenant-1", "campus-1")
            ] = (True, time.monotonic())

    updates = [
        make_mock_update(f"user-{u}", "document", f"doc-{r}")
        for u in range(10)
        for r in range(10)
    ]

    mock_redis = AsyncMock()
    mock_ws = AsyncMock()

    with (
        patch("app.deps.cache.get_cache", return_value=mock_redis),
        patch("app.services.ws_hub_client._get_client", return_value=mock_ws),
    ):
        await asyncio.gather(*[_invalidate_for_update(upd, cache) for upd in updates])

    for u in range(10):
        for r in range(10):
            key = (f"user-{u}", "document", f"doc-{r}", "read", "tenant-1", "campus-1")
            assert key not in cache, f"Key {key} should have been evicted"

    for u in range(10, 50):
        for r in range(10, 20):
            key = (f"user-{u}", "document", f"doc-{r}", "read", "tenant-1", "campus-1")
            assert key in cache, f"Key {key} should remain in cache"

    assert mock_redis.invalidate.call_count == 100
    assert mock_ws.publish_control_event.call_count == 100


@pytest.mark.anyio
async def test_concurrent_invalidate_with_simultaneous_cache_reads_and_writes():
    """Stress test concurrent cache reads/writes while invalidation is running."""
    cache = {
        ("user-1", "document", "doc-1", "read"): (True, time.monotonic()),
        ("user-2", "document", "doc-2", "read"): (True, time.monotonic()),
    }

    mock_redis = AsyncMock()

    async def delayed_invalidate(*args, **kwargs):
        await asyncio.sleep(0.001)

    mock_redis.invalidate.side_effect = delayed_invalidate
    mock_ws = AsyncMock()
    mock_ws.publish_control_event.side_effect = delayed_invalidate

    async def invalidation_worker():
        for i in range(20):
            upd = make_mock_update("user-1", "document", "doc-1")
            await _invalidate_for_update(upd, cache)

    async def reader_worker():
        for _ in range(50):
            _ = cache.get(("user-1", "document", "doc-1", "read"))
            await asyncio.sleep(0.0005)

    async def writer_worker():
        for i in range(30):
            cache[(f"user-new-{i}", "document", "doc-x", "read")] = (
                True,
                time.monotonic(),
            )
            await asyncio.sleep(0.0005)

    with (
        patch("app.deps.cache.get_cache", return_value=mock_redis),
        patch("app.services.ws_hub_client._get_client", return_value=mock_ws),
    ):
        await asyncio.gather(
            invalidation_worker(),
            invalidation_worker(),
            reader_worker(),
            writer_worker(),
        )

    assert ("user-1", "document", "doc-1", "read") not in cache
    assert len([k for k in cache if k[0].startswith("user-new-")]) == 30


@pytest.mark.anyio
async def test_prometheus_counter_increments_multiple_events():
    """Verify Prometheus counter increments across multiple watch events."""
    mock_redis = AsyncMock()
    mock_ws = AsyncMock()

    val_before_watch = (
        REGISTRY.get_sample_value(
            "spicedb_watch_events_total", {"event_type": "update"}
        )
        or 0.0
    )
    val_before_revoked = (
        REGISTRY.get_sample_value(
            "ws_hub_sessions_revoked_total", {"reason": "access_revoked"}
        )
        or 0.0
    )

    cache = {}
    N_EVENTS = 25
    updates = [
        make_mock_update(f"user-prom-{i}", "document", f"doc-{i}")
        for i in range(N_EVENTS)
    ]

    with (
        patch("app.deps.cache.get_cache", return_value=mock_redis),
        patch("app.services.ws_hub_client._get_client", return_value=mock_ws),
    ):
        for upd in updates:
            await _invalidate_for_update(upd, cache)

    val_after_watch = (
        REGISTRY.get_sample_value(
            "spicedb_watch_events_total", {"event_type": "update"}
        )
        or 0.0
    )
    val_after_revoked = (
        REGISTRY.get_sample_value(
            "ws_hub_sessions_revoked_total", {"reason": "access_revoked"}
        )
        or 0.0
    )

    assert val_after_watch == val_before_watch + N_EVENTS
    assert val_after_revoked == val_before_revoked + N_EVENTS


@pytest.mark.anyio
async def test_prometheus_counters_on_redis_nats_failures():
    """Verify metrics increment even when Redis or NATS errors occur."""
    mock_redis = AsyncMock()
    mock_redis.invalidate.side_effect = RuntimeError("Redis connection lost")

    mock_ws = AsyncMock()
    mock_ws.publish_control_event.side_effect = TimeoutError("NATS timeout")

    val_before_watch = (
        REGISTRY.get_sample_value(
            "spicedb_watch_events_total", {"event_type": "update"}
        )
        or 0.0
    )
    val_before_revoked = (
        REGISTRY.get_sample_value(
            "ws_hub_sessions_revoked_total", {"reason": "access_revoked"}
        )
        or 0.0
    )

    cache = {("user-err", "doc", "1", "read"): (True, time.monotonic())}
    upd = make_mock_update("user-err", "doc", "1")

    with (
        patch("app.deps.cache.get_cache", return_value=mock_redis),
        patch("app.services.ws_hub_client._get_client", return_value=mock_ws),
    ):
        await _invalidate_for_update(upd, cache)

    assert ("user-err", "doc", "1", "read") not in cache

    val_after_watch = (
        REGISTRY.get_sample_value(
            "spicedb_watch_events_total", {"event_type": "update"}
        )
        or 0.0
    )
    val_after_revoked = (
        REGISTRY.get_sample_value(
            "ws_hub_sessions_revoked_total", {"reason": "access_revoked"}
        )
        or 0.0
    )

    assert val_after_watch == val_before_watch + 1.0
    assert val_after_revoked == val_before_revoked + 1.0


@pytest.mark.anyio
async def test_batch_update_stream_performance():
    """Stress test batch of 50 updates arriving in a single watch response."""
    mock_channel = AsyncMock()
    mock_stub = AsyncMock()

    batch_updates = [
        make_mock_update(f"user-batch-{i}", "document", f"doc-{i}") for i in range(50)
    ]
    mock_response = AsyncMock()
    mock_response.updates = batch_updates

    async def mock_watch_stream(*args, **kwargs):
        yield mock_response

    mock_stub.Watch = mock_watch_stream
    mock_redis = AsyncMock()
    mock_ws = AsyncMock()

    cache = {
        (f"user-batch-{i}", "document", f"doc-{i}", "read"): (True, time.monotonic())
        for i in range(50)
    }

    with (
        patch("grpc.aio.insecure_channel", return_value=mock_channel),
        patch("authzed.api.v1.WatchServiceStub", return_value=mock_stub),
        patch("app.auth.rbac._permission_cache", cache),
        patch("app.deps.cache.get_cache", return_value=mock_redis),
        patch("app.services.ws_hub_client._get_client", return_value=mock_ws),
    ):
        start_time = time.monotonic()
        await _watch_once("token", "localhost", 50051, False)
        elapsed = time.monotonic() - start_time

    # All 50 entries evicted
    assert len(cache) == 0
    # Processed under 1 second
    assert elapsed < 1.0
    assert mock_redis.invalidate.call_count == 50
    assert mock_ws.publish_control_event.call_count == 50
