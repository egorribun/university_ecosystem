"""Deterministic closure tests for UserAnalyticsService."""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import stats_cache
from app.services.user.analytics_service import UserAnalyticsService

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return list(self._rows)


class _Database:
    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _statement):
        return self._results.pop(0)


@pytest.fixture
def cache_disabled(monkeypatch):
    monkeypatch.setattr(stats_cache, "get_cached_stats", AsyncMock(return_value=None))
    monkeypatch.setattr(stats_cache, "set_cached_stats", AsyncMock())


def test_datetime_and_grade_payload_normalization():
    service = UserAnalyticsService(SimpleNamespace())

    assert service._dt_to_iso(None) == ""
    naive = datetime(2026, 6, 1, 12, 0)
    assert service._dt_to_iso(naive) == "2026-06-01T12:00:00+00:00"
    plus3 = datetime(2026, 6, 1, 15, 0, tzinfo=timezone(timedelta(hours=3)))
    assert service._dt_to_iso(plus3) == "2026-06-01T12:00:00+00:00"

    assert (
        service._parse_grade_payload(None, fallback_title="T", fallback_date=NOW)
        is None
    )
    assert (
        service._parse_grade_payload("", fallback_title="T", fallback_date=NOW) is None
    )
    assert (
        service._parse_grade_payload("not-json", fallback_title="T", fallback_date=NOW)
        is None
    )
    assert (
        service._parse_grade_payload("[]", fallback_title="T", fallback_date=NOW)
        is None
    )
    assert (
        service._parse_grade_payload(
            '{"course": "T"}', fallback_title="T", fallback_date=NOW
        )
        is None
    )
    assert (
        service._parse_grade_payload(
            '{"score": "bad"}', fallback_title="T", fallback_date=NOW
        )
        is None
    )
    no_max = service._parse_grade_payload(
        '{"score": 3}', fallback_title="T", fallback_date=NOW
    )
    assert no_max is not None
    assert no_max["max"] is None

    fallback = service._parse_grade_payload(
        '{"score": 4.5, "max": "bad", "course": " ", "date": "bad"}',
        fallback_title="Algebra",
        fallback_date=NOW,
    )
    assert fallback == {
        "course": "Algebra",
        "score": 4.5,
        "max": None,
        "date": "2026-06-01T12:00:00+00:00",
    }

    explicit = service._parse_grade_payload(
        '{"score": 87, "max": 100, "course": "Physics", '
        '"date": "2026-05-30T09:00:00+00:00"}',
        fallback_title="ignored",
        fallback_date=None,
    )
    assert explicit == {
        "course": "Physics",
        "score": 87.0,
        "max": 100.0,
        "date": "2026-05-30T09:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_attendance_stats_empty_and_recent_rows(cache_disabled):
    service = UserAnalyticsService(_Database([]))
    empty = await service.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert empty["percent"] == 0.0
    assert empty["recent"] == []

    starts = NOW - timedelta(days=1)
    registered = NOW - timedelta(days=2)
    rows = [
        SimpleNamespace(starts_at=starts, registered_at=registered, title="Math"),
        SimpleNamespace(starts_at=None, registered_at=registered, title=None),
    ]
    service = UserAnalyticsService(_Database(rows))
    result = await service.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=30, period_key="month", skip_cache=True
    )

    assert result["percent"] == 100.0
    assert result["total"] == 2
    assert result["period_key"] == "month"
    assert result["recent"][0]["course"] == "Math"
    assert result["recent"][1]["course"] is None


@pytest.mark.asyncio
async def test_attendance_cached_payload_short_circuits_db(monkeypatch):
    payload = {"cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=payload)),
    )
    service = UserAnalyticsService(_Database())

    assert (
        await service.get_attendance_stats(
            user_id=uuid.uuid4(), period_days=7, skip_cache=False
        )
        is payload
    )


@pytest.mark.asyncio
async def test_grade_stats_empty_and_scale_with_invalid_and_zero_entries(
    cache_disabled,
):
    empty = UserAnalyticsService(_Database(_ScalarResult([])))
    empty_result = await empty.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert empty_result["average"] == 0.0
    assert empty_result["scale"] == "5"

    notifications = [
        SimpleNamespace(
            body='{"score": 87, "max": 100, "course": "Physics"}',
            title="Physics",
            created_at=NOW,
        ),
        SimpleNamespace(body='{"score": 0, "max": 5}', title="Zero", created_at=NOW),
        SimpleNamespace(body="not-json", title="Bad", created_at=NOW),
        SimpleNamespace(body=None, title="Empty", created_at=NOW),
    ]
    service = UserAnalyticsService(_Database(_ScalarResult(notifications)))
    result = await service.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )

    assert result["total_grades"] == 2
    assert result["average"] == pytest.approx(43.5)
    assert result["scale"] == "100"
    assert len(result["recent"]) == 2


@pytest.mark.asyncio
async def test_grade_stats_cached_payload_short_circuits_db(monkeypatch):
    payload = {"average": 5.0, "cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=payload)),
    )
    service = UserAnalyticsService(_Database())

    assert (
        await service.get_grade_stats(
            user_id=uuid.uuid4(), period_days=7, skip_cache=False
        )
        is payload
    )


@pytest.mark.asyncio
async def test_participation_stats_empty_and_recent_rows(cache_disabled):
    service = UserAnalyticsService(_Database([]))
    empty = await service.get_participation_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert empty["events"] == 0
    assert empty["recent"] == []

    starts = NOW - timedelta(days=1)
    rows = [
        (NOW - timedelta(days=2), starts, "Hackathon", "hackathon"),
        (NOW - timedelta(days=3), None, None, None),
    ]
    service = UserAnalyticsService(_Database(rows))
    result = await service.get_participation_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )

    assert result["events"] == 2
    assert result["hours"] == 0.0
    assert result["recent"][0]["title"] == "Hackathon"
    assert result["recent"][0]["role"] == "hackathon"
    assert result["recent"][1]["title"] == ""
    assert result["recent"][1]["role"] is None


@pytest.mark.asyncio
async def test_participation_cached_payload_short_circuits_db(monkeypatch):
    payload = {"events": 9, "cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=payload)),
    )
    service = UserAnalyticsService(_Database())

    assert (
        await service.get_participation_stats(
            user_id=uuid.uuid4(), period_days=7, skip_cache=False
        )
        is payload
    )
