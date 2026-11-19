"""Closure tests for CQRS schedule and statistics query handlers."""

from __future__ import annotations

import hashlib
import json
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
async def test_schedule_handler_reads_repository_on_every_request():
    db = AsyncMock()
    handler = GetScheduleHandler(db)
    row = _schedule()
    changed = row.model_copy(update={"subject": "Physics"})
    group_id = uuid4()

    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        read = AsyncMock(side_effect=[[row], [changed]])
        repository_type.return_value.get_by_group = read
        result = await handler.handle(
            GetScheduleQuery(group_id=str(group_id), locale="en", if_none_match=None)
        )
        next_result = await handler.handle(
            GetScheduleQuery(group_id=str(group_id), locale="en", if_none_match=None)
        )

    assert repository_type.call_count == 2
    assert all(call.args == (db,) for call in repository_type.call_args_list)
    assert read.await_count == 2
    assert all(call.args == (group_id,) for call in read.await_args_list)
    assert result.payload[0]["lesson_type_display"] == "Lecture"
    assert result.etag is not None
    assert result.payload[0]["subject"] == "Mathematics"
    assert next_result.payload[0]["subject"] == "Physics"
    assert next_result.etag != result.etag


@pytest.mark.asyncio
async def test_schedule_handler_localizes_repository_result():
    db = AsyncMock()
    handler = GetScheduleHandler(db)
    row = _schedule()
    group_id = uuid4()

    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        read = AsyncMock(return_value=[row])
        repository_type.return_value.get_by_group = read
        result = await handler.handle(
            GetScheduleQuery(group_id=group_id, locale="ru", if_none_match=None)
        )

    assert result.etag is not None
    assert result.payload[0]["lesson_type_display"] == "Лекция"
    repository_type.assert_called_once_with(db)
    read.assert_awaited_once_with(group_id)


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
    representation_hash = hashlib.sha256(
        json.dumps(
            result.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    assert result.etag == f'"{representation_hash}"'
    assert result.etag != f'"{entry.etag}"'
    get_cached.assert_awaited_once()
    analytics.get_grade_stats.assert_not_awaited()

    query.if_none_match = f'"{entry.etag}"'
    with patch(
        "app.cqrs.queries.stats_cache.get_cached_stats",
        new=AsyncMock(return_value=entry),
    ):
        legacy_validator = await handler.handle(query)
    assert legacy_validator.not_modified is False
    assert legacy_validator.payload == result.payload
    assert legacy_validator.etag == result.etag

    query.if_none_match = result.etag
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


@pytest.mark.asyncio
async def test_schedule_validator_tracks_current_localized_rows():
    row = _schedule()
    handler = GetScheduleHandler(AsyncMock())
    query = GetScheduleQuery(group_id=row.group_id, locale="en", if_none_match=None)
    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        read = AsyncMock(return_value=[row])
        repository_type.return_value.get_by_group = read
        english = await handler.handle(query)
        query.locale = "ru"
        query.if_none_match = english.etag
        russian = await handler.handle(query)
        assert russian.not_modified is False
        assert russian.etag != english.etag
        assert russian.payload[0]["lesson_type_display"] == "Лекция"
        query.if_none_match = russian.etag
        unchanged = await handler.handle(query)
        assert unchanged.not_modified is True
        read.return_value = []
        removed = await handler.handle(query)
        assert removed.payload == []
        assert removed.not_modified is False
        assert read.await_count == 4
        assert all(call.args == (row.group_id,) for call in read.await_args_list)


@pytest.mark.asyncio
async def test_schedule_database_failure_propagates_even_with_matching_validator():
    from sqlalchemy.exc import SQLAlchemyError

    row = _schedule()
    handler = GetScheduleHandler(AsyncMock())
    query = GetScheduleQuery(group_id=row.group_id, locale="en", if_none_match=None)
    with patch("app.cqrs.queries.ScheduleRepository") as repository_type:
        read = AsyncMock(side_effect=[[row], SQLAlchemyError("database unavailable")])
        repository_type.return_value.get_by_group = read
        initial = await handler.handle(query)
        query.if_none_match = initial.etag
        with pytest.raises(SQLAlchemyError, match="database unavailable"):
            await handler.handle(query)
        assert read.await_count == 2
