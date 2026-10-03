"""Behavior and calculation tests for user analytics services.

Pure-function coverage for ``_dt_to_iso`` (mirrors
tests/test_notification_templates_units.py) plus real-DB coverage for the three
stats methods with ``skip_cache=True`` (mirrors the repository-tier recipe:
real ``user_factory()`` ids through all FKs, explicit recent ``created_at``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.services import stats_cache
from app.services.user.analytics_service import UserAnalyticsService


@pytest.fixture
def svc(db_session: AsyncSession) -> UserAnalyticsService:
    return UserAnalyticsService(db_session)


# ---------------------------------------------------------------------------
# _dt_to_iso
# ---------------------------------------------------------------------------


def test_dt_to_iso_none_returns_empty(svc):
    assert svc._dt_to_iso(None) == ""


def test_dt_to_iso_naive_coerced_to_utc(svc):
    naive = datetime(2026, 6, 1, 12, 0, 0)
    assert svc._dt_to_iso(naive) == "2026-06-01T12:00:00+00:00"


def test_dt_to_iso_aware_converted_to_utc(svc):
    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert svc._dt_to_iso(aware) == "2026-06-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Real-DB fixtures
# ---------------------------------------------------------------------------


async def _add_attended_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str = "Event",
    event_type: str | None = "workshop",
    hours_ago: int = 2,
) -> models.Event:
    """Event in the recent past (inside any period window) + attendance row."""
    now = datetime.now(UTC)
    starts = now - timedelta(hours=hours_ago)
    event = models.Event(
        title=title,
        event_type=event_type,
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
        created_by=user_id,
        is_active=True,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    attendance = models.EventAttendance(
        event_id=event.id,
        user_id=user_id,
        qr_secret="qr-secret",  # pragma: allowlist secret
        qr_hmac="qr-hmac",  # pragma: allowlist secret
        registered_at=now,
    )
    db.add(attendance)
    await db.flush()
    return event


async def _add_grade(
    db: AsyncSession,
    student_id: uuid.UUID,
    *,
    score: float,
    subject: str = "Math",
    days_ago: float = 1,
) -> models.Grade:
    grade = models.Grade(
        student_id=student_id,
        subject=subject,
        score=score,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(grade)
    await db.flush()
    return grade


# ---------------------------------------------------------------------------
# get_attendance_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attendance_stats_empty(svc, user_factory):
    user = await user_factory()
    result = await svc.get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result["percent"] == 0.0
    assert result["total"] == 0
    assert result["recent"] == []


@pytest.mark.asyncio
async def test_attendance_stats_with_recent_events(svc, db_session, user_factory):
    user = await user_factory()
    await _add_attended_event(db_session, user.id, title="Lecture A")
    await _add_attended_event(db_session, user.id, title="Lecture B", hours_ago=4)

    result = await svc.get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result["percent"] == 100.0
    assert result["present"] == 2
    assert result["total"] == 2
    assert result["trend"] == 100.0
    courses = {item["course"] for item in result["recent"]}
    assert courses == {"Lecture A", "Lecture B"}
    assert all(item["status"] == "present" for item in result["recent"])


@pytest.mark.asyncio
async def test_attendance_percent_counts_events_without_registration(
    svc, db_session, user_factory
):
    user = await user_factory()
    other = await user_factory()
    await _add_attended_event(db_session, user.id, title="Mine")
    await _add_attended_event(db_session, other.id, title="Not mine")

    result = await svc.get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result["present"] == 1
    assert result["total"] == 2
    assert result["percent"] == 50.0
    assert [item["course"] for item in result["recent"]] == ["Mine"]


@pytest.mark.asyncio
async def test_attendance_stats_returns_cached_payload(svc, user_factory, monkeypatch):
    user = await user_factory()
    sentinel = {"percent": 42.0, "cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=sentinel)),
    )
    result = await svc.get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=False
    )
    assert result is sentinel


# ---------------------------------------------------------------------------
# get_grade_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_stats_average_trend_and_recent(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade(db_session, user.id, score=4, subject="Math", days_ago=1)
    await _add_grade(db_session, user.id, score=5, subject="Physics", days_ago=2)
    # Previous window (31-60 days ago).
    await _add_grade(db_session, user.id, score=3, subject="Old", days_ago=40)

    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 2
    assert result["average"] == pytest.approx(4.5)
    assert result["trend"] == pytest.approx(1.5)
    assert result["scale"] == "5"
    assert [item["course"] for item in result["recent"]] == ["Math", "Physics"]
    assert result["recent"][0]["score"] == 4.0
    assert result["recent"][0]["max"] is None


@pytest.mark.asyncio
async def test_grade_stats_detects_100_scale(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade(db_session, user.id, score=87, subject="Chemistry")
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["scale"] == "100"
    assert result["average"] == pytest.approx(87.0)


@pytest.mark.asyncio
async def test_grade_stats_limits_recent_to_five(svc, db_session, user_factory):
    user = await user_factory()
    for index in range(7):
        await _add_grade(db_session, user.id, score=4, days_ago=index + 1)
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 7
    assert len(result["recent"]) == 5


@pytest.mark.asyncio
async def test_grade_stats_ignores_other_students(svc, db_session, user_factory):
    user = await user_factory()
    other = await user_factory()
    await _add_grade(db_session, other.id, score=5)
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 0
    assert result["average"] == 0.0
    assert result["recent"] == []


@pytest.mark.asyncio
async def test_grade_stats_handles_zero_score(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade(db_session, user.id, score=0)
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 1
    assert result["average"] == 0.0


@pytest.mark.asyncio
async def test_grade_stats_returns_cached_payload(svc, user_factory, monkeypatch):
    user = await user_factory()
    sentinel = {"average": 5.0, "cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=sentinel)),
    )
    result = await svc.get_grade_stats(
        user_id=user.id, period_days=30, skip_cache=False
    )
    assert result is sentinel


@pytest.mark.asyncio
async def test_computed_stats_are_written_to_cache(svc, user_factory, monkeypatch):
    user = await user_factory()
    monkeypatch.setattr(stats_cache, "get_cached_stats", AsyncMock(return_value=None))
    setter = AsyncMock()
    monkeypatch.setattr(stats_cache, "set_cached_stats", setter)
    result = await svc.get_grade_stats(user_id=user.id, period_days=7)
    setter.assert_awaited_once()
    assert setter.await_args.kwargs["kind"] == "grades"
    assert setter.await_args.kwargs["payload"] is result


# ---------------------------------------------------------------------------
# get_participation_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_participation_stats_with_events(svc, db_session, user_factory):
    user = await user_factory()
    await _add_attended_event(
        db_session, user.id, title="Hackathon", event_type="hackathon"
    )

    result = await svc.get_participation_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result["events"] == 1
    assert result["hours"] == 1.0
    assert result["groups"] == 1
    assert result["trend"] == 1
    assert result["recent"][0]["title"] == "Hackathon"
    assert result["recent"][0]["role"] == "hackathon"


@pytest.mark.asyncio
async def test_participation_stats_empty(svc, user_factory):
    user = await user_factory()
    result = await svc.get_participation_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result["events"] == 0
    assert result["recent"] == []


@pytest.mark.asyncio
async def test_participation_stats_returns_cached_payload(
    svc, user_factory, monkeypatch
):
    user = await user_factory()
    sentinel = {"events": 9, "cached": True}
    monkeypatch.setattr(
        stats_cache,
        "get_cached_stats",
        AsyncMock(return_value=SimpleNamespace(payload=sentinel)),
    )
    result = await svc.get_participation_stats(
        user_id=user.id, period_days=30, skip_cache=False
    )
    assert result is sentinel
