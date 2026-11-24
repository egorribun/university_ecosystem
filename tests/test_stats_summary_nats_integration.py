from __future__ import annotations

import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.cqrs.queries import GetStatsHandler
from app.services import stats_cache
from app.services import stats_fill_fence as fence_module
from app.services.user.analytics_service import UserAnalyticsService
from tests.test_stats_fill_fence_nats_barrier import setup
from tests.test_stats_summary_fence import KINDS, SnapshotRepository, query


def nats_handler(ttl_enabled):
    cache, kv, _ = setup(ttl_enabled)
    repo = SnapshotRepository()
    analytics = UserAnalyticsService(None)
    analytics.stats_repo = repo
    return GetStatsHandler(None, cache, analytics), cache, kv, repo, uuid4()


async def read_summary(handler, user_id):
    queries = tuple(query(user_id, kind) for kind in KINDS)
    return await handler.handle_summary(queries)


async def cached_sections(cache, user_id):
    return [
        await stats_cache.get_cached_stats(
            cache=cache, kind=kind, user_id=user_id, period_key="30d"
        )
        for kind in KINDS
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl_enabled", [False, True])
async def test_nats_summary_cold_fill_and_warm_hit_without_unconditional_set(
    ttl_enabled,
):
    handler, cache, _kv, repo, user_id = nats_handler(ttl_enabled)
    cache.set = AsyncMock(wraps=cache.set)
    cold = await read_summary(handler, user_id)
    assert repo.requested == [frozenset(KINDS)]
    assert all(entry is not None for entry in await cached_sections(cache, user_id))
    for kind in KINDS:
        key = stats_cache.make_stats_cache_key(kind, user_id, "30d")
        entry = await cache.get(key)
        assert entry is not None and entry.ttl_seconds == float(
            settings.stats_cache_ttl_seconds
        )
    warm = await read_summary(handler, user_id)
    assert [item.payload for item in warm] == [item.payload for item in cold]
    assert [item.etag for item in warm] == [item.etag for item in cold]
    assert repo.requested == [frozenset(KINDS)]
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_stage", ["reserve", "barrier", "fill"])
async def test_nats_summary_lost_ack_never_unconditionally_fills_and_recovers(
    monkeypatch, lost_stage
):
    clock = [time.time()]
    monkeypatch.setattr(fence_module.time, "time", lambda: clock[0])
    handler, cache, kv, repo, user_id = nats_handler(False)
    cache.set = AsyncMock(wraps=cache.set)
    kv.lost_stage = lost_stage
    first = await read_summary(handler, user_id)
    assert first[1].payload["average"] == 3.0
    assert repo.requested == [frozenset(KINDS)]
    entries = await cached_sections(cache, user_id)
    if lost_stage == "fill":
        assert all(entry is not None for entry in entries)
        kv.lost_stage = None
        warm = await read_summary(handler, user_id)
        assert [item.etag for item in warm] == [item.etag for item in first]
        assert repo.requested == [frozenset(KINDS)]
    else:
        assert all(entry is None for entry in entries)
        kv.lost_stage = None
        await read_summary(handler, user_id)
        assert all(entry is None for entry in await cached_sections(cache, user_id))
        clock[0] += 31
        await read_summary(handler, user_id)
        assert all(entry is not None for entry in await cached_sections(cache, user_id))
        calls = len(repo.requested)
        await read_summary(handler, user_id)
        assert len(repo.requested) == calls
    cache.set.assert_not_awaited()
