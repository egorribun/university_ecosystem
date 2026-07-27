"""Coverage tests for app/services/user/analytics_service.py (testing session 9).

Pure-function coverage for ``_dt_to_iso`` / ``_parse_grade_payload`` (mirrors
tests/test_notification_templates_units.py) plus real-DB coverage for the three
stats methods with ``skip_cache=True`` (mirrors the repository-tier recipe:
real ``user_factory()`` ids through all FKs, explicit recent ``created_at``).
"""

from __future__ import annotations

import json
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
# _parse_grade_payload
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "not-json{",
        json.dumps(["not", "a", "dict"]),
        json.dumps({"no_score": 1}),
        json.dumps({"score": "not-a-number"}),
    ],
)
def test_parse_grade_payload_rejects_invalid(svc, body):
    assert (
        svc._parse_grade_payload(body, fallback_title="T", fallback_date=None) is None
    )


def test_parse_grade_payload_full_payload(svc):
    body = json.dumps(
        {"score": 4.5, "max": 5, "course": "Math", "date": "2026-06-01T10:00:00+00:00"}
    )
    parsed = svc._parse_grade_payload(
        body, fallback_title="Fallback", fallback_date=None
    )
    assert parsed == {
        "course": "Math",
        "score": 4.5,
        "max": 5.0,
        "date": "2026-06-01T10:00:00+00:00",
    }


def test_parse_grade_payload_fallbacks(svc):
    """Non-numeric max → None; blank course → fallback title; bad date → fallback date."""
    fallback_dt = datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)
    body = json.dumps(
        {"score": "3", "max": "abc", "course": "  ", "date": "not-a-date"}
    )
    parsed = svc._parse_grade_payload(
        body, fallback_title="Physics", fallback_date=fallback_dt
    )
    assert parsed is not None
    assert parsed["score"] == 3.0
    assert parsed["max"] is None
    assert parsed["course"] == "Physics"
    assert parsed["date"] == "2026-06-02T09:00:00+00:00"


def test_parse_grade_payload_non_string_date_uses_fallback(svc):
    body = json.dumps({"score": 5, "date": 12345})
    parsed = svc._parse_grade_payload(body, fallback_title="T", fallback_date=None)
    assert parsed is not None
    assert parsed["date"] == ""


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


async def _add_grade_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    payload: dict | str | None,
    title: str = "Grade",
) -> models.Notification:
    now = datetime.now(UTC)
    body = (
        payload if isinstance(payload, str) or payload is None else json.dumps(payload)
    )
    notif = models.Notification(
        user_id=user_id,
        title=title,
        body=body,
        type="grade",
        created_at=now,
        read=False,
    )
    db.add(notif)
    await db.flush()
    return notif


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
    courses = {item["course"] for item in result["recent"]}
    assert courses == {"Lecture A", "Lecture B"}
    assert all(item["status"] == "present" for item in result["recent"])


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
async def test_grade_stats_parses_and_averages(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade_notification(
        db_session, user.id, payload={"score": 4, "max": 5, "course": "Math"}
    )
    await _add_grade_notification(
        db_session, user.id, payload={"score": 5, "max": 5, "course": "Physics"}
    )
    # Unparseable body is skipped without breaking the aggregate.
    await _add_grade_notification(db_session, user.id, payload="not-json{")

    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 2
    assert result["average"] == pytest.approx(4.5)
    assert result["scale"] == "5"
    assert len(result["recent"]) == 2


@pytest.mark.asyncio
async def test_grade_stats_detects_100_scale(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade_notification(
        db_session, user.id, payload={"score": 87, "max": 100, "course": "Chemistry"}
    )
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["scale"] == "100"
    assert result["average"] == pytest.approx(87.0)


@pytest.mark.asyncio
async def test_grade_stats_empty(svc, user_factory):
    user = await user_factory()
    result = await svc.get_grade_stats(user_id=user.id, period_days=30, skip_cache=True)
    assert result["total_grades"] == 0
    assert result["average"] == 0.0
    assert result["recent"] == []


@pytest.mark.asyncio
async def test_grade_stats_handles_zero_score(svc, db_session, user_factory):
    user = await user_factory()
    await _add_grade_notification(
        db_session,
        user.id,
        payload={"score": 0, "max": 5, "course": "Math"},
    )

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
