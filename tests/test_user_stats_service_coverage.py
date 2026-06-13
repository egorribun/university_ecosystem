"""Coverage tests for app/services/user/stats_service.py (testing session 10).

AsyncMock-repo harness (pattern A, mirrors tests/test_compliance_service_coverage.py).
NOTE: StatsService is currently UNWIRED in app/ (the live /stats/* path injects
UserAnalyticsService instead) — these tests pin its behavior so a future re-wiring
doesn't regress; deletion of the module is a separate product decision.

Covers: _dt_to_iso (None/naive/aware), _parse_grade_payload (all reject + fallback
branches), get_attendance_stats (empty + math + rn/date-source/title branches),
get_grade_stats (average/trend/scale/recent-cap/invalid-entry filtering),
get_participation_stats (duration clamp + unique groups + recent cap + trend).
All calls use skip_cache=True for the pure paths; one skip_cache=False sanity
call exercises the stats_cache.cache_stats wrapper against the conftest mock cache.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.user.stats_service import StatsService

NOW = datetime.now(UTC)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def svc(repo: AsyncMock) -> StatsService:
    return StatsService(stats_repo=repo)


def _attendance_row(
    *,
    rn: int | None = 1,
    current_total: int = 0,
    current_attended: int = 0,
    previous_total: int = 0,
    previous_attended: int = 0,
    starts_at: datetime | None = None,
    registered_at: datetime | None = None,
    title: str | None = "Lecture",
) -> SimpleNamespace:
    return SimpleNamespace(
        rn=rn,
        current_total=current_total,
        current_attended=current_attended,
        previous_total=previous_total,
        previous_attended=previous_attended,
        starts_at=starts_at,
        registered_at=registered_at,
        title=title,
    )


def _notification(body: str | None, *, title: str = "Course X") -> SimpleNamespace:
    return SimpleNamespace(body=body, title=title, created_at=NOW)


def _participation_row(
    *,
    hours: float = 2.0,
    event_type: str | None = "workshop",
    title: str = "Event",
    starts_at: datetime | None = None,
) -> SimpleNamespace:
    start = starts_at or NOW
    return SimpleNamespace(
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        event_type=event_type,
        title=title,
    )


# ---------------------------------------------------------------- _dt_to_iso


def test_dt_to_iso_none_returns_empty(svc: StatsService) -> None:
    assert svc._dt_to_iso(None) == ""


def test_dt_to_iso_naive_assumes_utc(svc: StatsService) -> None:
    naive = datetime(2026, 6, 1, 12, 0, 0)
    assert svc._dt_to_iso(naive) == "2026-06-01T12:00:00+00:00"


def test_dt_to_iso_aware_converts_to_utc(svc: StatsService) -> None:
    plus3 = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    assert svc._dt_to_iso(plus3) == "2026-06-01T12:00:00+00:00"


# ---------------------------------------------------- get_attendance_stats


async def test_attendance_empty_rows(svc: StatsService, repo: AsyncMock) -> None:
    repo.get_attendance_stats_raw.return_value = []
    result = await svc.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["percent"] == 0.0
    assert result["present"] == 0
    assert result["total"] == 0
    assert result["trend"] == 0.0
    assert result["period_key"] == "30d"
    assert result["recent"] == []


async def test_attendance_math_and_recent_branches(
    svc: StatsService, repo: AsyncMock
) -> None:
    starts = NOW - timedelta(days=1)
    registered = NOW - timedelta(days=2)
    repo.get_attendance_stats_raw.return_value = [
        _attendance_row(
            rn=1,
            current_total=4,
            current_attended=3,
            previous_total=2,
            previous_attended=1,
            starts_at=starts,
            title="Math",
        ),
        # rn=None rows are aggregate-only and must be skipped from `recent`
        _attendance_row(rn=None, starts_at=starts, title="Skipped"),
        # starts_at missing -> falls back to registered_at; empty title -> None
        _attendance_row(rn=2, starts_at=None, registered_at=registered, title=""),
    ]
    result = await svc.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["percent"] == 75.0
    assert result["present"] == 3
    assert result["total"] == 4
    assert result["trend"] == 25.0  # 75% now vs 50% previous
    assert len(result["recent"]) == 2
    assert result["recent"][0]["course"] == "Math"
    assert result["recent"][0]["date"] == starts.astimezone(UTC).isoformat()
    assert result["recent"][1]["course"] is None
    assert result["recent"][1]["date"] == registered.astimezone(UTC).isoformat()


async def test_attendance_with_cache_wrapper_path(
    svc: StatsService, repo: AsyncMock
) -> None:
    """skip_cache=False exercises the cache_stats decorator read+store path."""
    repo.get_attendance_stats_raw.return_value = []
    result = await svc.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=90, period_key="custom"
    )
    assert result["period_key"] == "custom"


async def test_attendance_period_key_fallback_to_days(
    svc: StatsService, repo: AsyncMock
) -> None:
    repo.get_attendance_stats_raw.return_value = []
    result = await svc.get_attendance_stats(
        user_id=uuid.uuid4(), period_days=180, period_key=None, skip_cache=True
    )
    assert result["period_key"] == "180d"


# -------------------------------------------------- _parse_grade_payload


def test_parse_grade_payload_empty_body(svc: StatsService) -> None:
    assert svc._parse_grade_payload(None, fallback_title="T", fallback_date=NOW) is None
    assert svc._parse_grade_payload("", fallback_title="T", fallback_date=NOW) is None


def test_parse_grade_payload_invalid_json(svc: StatsService) -> None:
    assert (
        svc._parse_grade_payload("{not json", fallback_title="T", fallback_date=NOW)
        is None
    )


def test_parse_grade_payload_non_dict(svc: StatsService) -> None:
    assert (
        svc._parse_grade_payload("[1, 2]", fallback_title="T", fallback_date=NOW)
        is None
    )


def test_parse_grade_payload_validation_error(svc: StatsService) -> None:
    assert (
        svc._parse_grade_payload('{"score": -1}', fallback_title="T", fallback_date=NOW)
        is None
    )


def test_parse_grade_payload_fallbacks(svc: StatsService) -> None:
    fallback_date = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    entry = svc._parse_grade_payload(
        '{"score": 4.5, "course": "  ", "date": "not-a-date"}',
        fallback_title="Algebra",
        fallback_date=fallback_date,
    )
    assert entry is not None
    assert entry["course"] == "Algebra"  # blank course -> fallback title
    assert entry["score"] == 4.5
    assert entry["max"] is None
    assert entry["date"] == "2026-06-01T10:00:00+00:00"  # bad date -> fallback


def test_parse_grade_payload_explicit_fields(svc: StatsService) -> None:
    entry = svc._parse_grade_payload(
        '{"score": 87, "max": 100, "course": "Physics", "date": "2026-05-30T09:00:00+00:00"}',
        fallback_title="ignored",
        fallback_date=None,
    )
    assert entry is not None
    assert entry["course"] == "Physics"
    assert entry["max"] == 100
    assert entry["date"] == "2026-05-30T09:00:00+00:00"


# ------------------------------------------------------- get_grade_stats


async def test_grade_stats_empty(svc: StatsService, repo: AsyncMock) -> None:
    repo.get_grade_notifications.return_value = []
    result = await svc.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["average"] == 0.0
    assert result["scale"] == "5"
    assert result["trend"] == 0.0
    assert result["recent"] == []
    assert result["period_key"] == "30d"


async def test_grade_stats_average_trend_and_filtering(
    svc: StatsService, repo: AsyncMock
) -> None:
    current = [
        _notification('{"score": 5}'),
        _notification('{"score": 4}'),
        _notification("not json"),  # filtered out
        _notification(None),  # filtered out
    ]
    previous = [_notification('{"score": 3}')]
    repo.get_grade_notifications.side_effect = [current, previous]
    result = await svc.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["average"] == 4.5
    assert result["trend"] == 1.5  # 4.5 - 3.0
    assert result["scale"] == "5"
    assert len(result["recent"]) == 2


async def test_grade_stats_scale_100_via_max(
    svc: StatsService, repo: AsyncMock
) -> None:
    repo.get_grade_notifications.side_effect = [
        [_notification('{"score": 4, "max": 100}')],
        [],
    ]
    result = await svc.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["scale"] == "100"


async def test_grade_stats_scale_100_via_score(
    svc: StatsService, repo: AsyncMock
) -> None:
    repo.get_grade_notifications.side_effect = [
        [_notification('{"score": 87}')],
        [],
    ]
    result = await svc.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["scale"] == "100"


async def test_grade_stats_recent_capped_at_five(
    svc: StatsService, repo: AsyncMock
) -> None:
    current = [_notification(f'{{"score": {i}}}') for i in range(1, 8)]
    repo.get_grade_notifications.side_effect = [current, []]
    result = await svc.get_grade_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert len(result["recent"]) == 5


# ----------------------------------------------- get_participation_stats


async def test_participation_empty(svc: StatsService, repo: AsyncMock) -> None:
    repo.get_participation_stats_raw.return_value = []
    result = await svc.get_participation_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["events"] == 0
    assert result["hours"] == 0.0
    assert result["groups"] == 0
    assert result["trend"] == 0
    assert result["recent"] == []


async def test_participation_math_groups_and_recent_cap(
    svc: StatsService, repo: AsyncMock
) -> None:
    rows: list[Any] = [
        _participation_row(hours=2.0, event_type="workshop", title="A"),
        _participation_row(hours=1.5, event_type="lecture", title="B"),
        _participation_row(hours=-1.0, event_type="workshop", title="C"),  # clamped
        _participation_row(hours=0.5, event_type=None, title="D"),
        _participation_row(hours=0.5, event_type="lecture", title="E"),
        _participation_row(hours=0.5, event_type="lecture", title="F"),
    ]
    repo.get_participation_stats_raw.return_value = rows
    result = await svc.get_participation_stats(
        user_id=uuid.uuid4(), period_days=30, skip_cache=True
    )
    assert result["events"] == 6
    assert result["hours"] == 5.0  # negative duration clamped to 0
    assert result["groups"] == 2  # workshop + lecture; None excluded
    assert result["trend"] == 1
    assert len(result["recent"]) == 5  # capped
    assert result["recent"][0]["title"] == "A"
