"""Closure tests for CQRS schedule and statistics query handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.cqrs.queries import (
    GetScheduleHandler,
    GetScheduleQuery,
    GetStatsHandler,
    GetStatsQuery,
)
from app.deps.cache import CacheEntry, MemoryCache, NullCache
from app.schemas.dtos.schedule import ScheduleDTO


def _schedule() -> ScheduleDTO:
    return ScheduleDTO(
        id=uuid4(),
        group_id=uuid4(),
        weekday="monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
        subject="Mathematics",
        teacher="Dr. Test",
        room="101",
        parity="both",
        lesson_type="lecture",
        creator_id=None,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_schedule_handler_reads_repository_and_populates_enabled_cache():
    db = AsyncMock()
    cache = MemoryCache(default_ttl=300)
    handler = GetScheduleHandler(db, cache)
    row = _schedule()
    group_id = uuid4()

    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        repository_type.return_value.get_by_group = AsyncMock(return_value=[row])
        result = await handler.handle(
            GetScheduleQuery(group_id=str(group_id), locale="en", if_none_match=None)
        )

    repository_type.assert_called_once_with(db)
    repository_type.return_value.get_by_group.assert_awaited_once_with(group_id)
    assert result.payload[0]["lesson_type_display"] == "Lecture"
    assert result.etag is not None
    assert await cache.get(f"schedule:group:{group_id}") is not None


@pytest.mark.asyncio
async def test_schedule_handler_reads_repository_without_cache():
    db = AsyncMock()
    handler = GetScheduleHandler(db, NullCache())
    row = _schedule()
    group_id = uuid4()

    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        repository_type.return_value.get_by_group = AsyncMock(return_value=[row])
        result = await handler.handle(
            GetScheduleQuery(group_id=group_id, locale="ru", if_none_match=None)
        )

    assert result.etag is None
    assert result.payload[0]["lesson_type_display"] == "Лекция"


def _stats_query(kind: str, *, skip_cache: bool = True, if_none_match=None):
    return GetStatsQuery(
        kind=kind,  # type: ignore[arg-type]
        user_id=uuid4(),
        period_key="month",
        period_days=30,
        locale="en",
        if_none_match=if_none_match,
        skip_cache=skip_cache,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["attendance", "grades", "participation"])
async def test_stats_handler_computes_each_supported_kind(kind):
    cache = MemoryCache(default_ttl=300)
    analytics = MagicMock()
    analytics.get_attendance_stats = AsyncMock(return_value={"period_key": "week"})
    analytics.get_grade_stats = AsyncMock(return_value={"score": 4.5})
    analytics.get_participation_stats = AsyncMock(return_value={})
    handler = GetStatsHandler(AsyncMock(), cache, analytics)

    result = await handler.handle(_stats_query(kind))

    assert result.payload["period_label"]
    assert result.etag is not None
    getattr(
        analytics, f"get_{'grade' if kind == 'grades' else kind}_stats"
    ).assert_awaited_once()


@pytest.mark.asyncio
async def test_stats_handler_uses_cached_payload_and_etag_not_modified():
    cache = MemoryCache(default_ttl=300)
    analytics = MagicMock()
    analytics.get_grade_stats = AsyncMock()
    handler = GetStatsHandler(AsyncMock(), cache, analytics)
    entry = CacheEntry(etag="stats-etag", payload={"score": 4}, stored_at=0)
    query = _stats_query("grades", skip_cache=False)

    with patch(
        "app.cqrs.queries.stats_cache.get_cached_stats",
        new=AsyncMock(return_value=entry),
    ) as get_cached:
        result = await handler.handle(query)

    assert result.payload["period_key"] == "month"
    assert result.etag == '"stats-etag"'
    get_cached.assert_awaited_once()
    analytics.get_grade_stats.assert_not_awaited()

    query.if_none_match = '"stats-etag"'
    with patch(
        "app.cqrs.queries.stats_cache.get_cached_stats",
        new=AsyncMock(return_value=entry),
    ):
        not_modified = await handler.handle(query)
    assert not_modified.not_modified is True
    assert not_modified.payload is None


@pytest.mark.asyncio
async def test_stats_handler_computes_when_cache_misses():
    cache = MemoryCache(default_ttl=300)
    analytics = MagicMock()
    analytics.get_attendance_stats = AsyncMock(return_value={"score": 3})
    handler = GetStatsHandler(AsyncMock(), cache, analytics)

    with patch(
        "app.cqrs.queries.stats_cache.get_cached_stats",
        new=AsyncMock(return_value=None),
    ) as get_cached:
        result = await handler.handle(_stats_query("attendance", skip_cache=False))

    assert result.payload["score"] == 3
    get_cached.assert_awaited_once()
    analytics.get_attendance_stats.assert_awaited_once()


@pytest.mark.asyncio
async def test_stats_handler_skip_cache_and_unknown_kind():
    analytics = MagicMock()
    analytics.get_attendance_stats = AsyncMock(return_value={})
    analytics.get_grade_stats = AsyncMock(return_value={})
    analytics.get_participation_stats = AsyncMock(return_value={})
    handler = GetStatsHandler(AsyncMock(), NullCache(), analytics)

    with patch("app.cqrs.queries.stats_cache.get_cached_stats") as get_cached:
        result = await handler.handle(_stats_query("attendance", skip_cache=False))
    assert result.payload["period_key"] == "month"
    get_cached.assert_not_called()

    with pytest.raises(HTTPException, match="Unknown stats kind"):
        await handler.handle(_stats_query("unknown"))
