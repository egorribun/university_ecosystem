"""Persisted activity windows and cache behavior through the public service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.deps.cache import MemoryCache
from app.schemas.events import EventCreate
from app.services.stats_cache import invalidate_user_stats_cache
from app.services.user import analytics_service
from app.services.user.analytics_service import UserAnalyticsService

NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_analytics_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(analytics_service, "datetime", FixedDatetime)


async def add_event(
    db: AsyncSession,
    creator_id: uuid.UUID,
    *,
    title: str,
    starts_at: datetime,
    attendee_id: uuid.UUID | None = None,
    duration: timedelta = timedelta(hours=1),
    event_type: str | None = "workshop",
    active: bool = True,
    registered_at: datetime = NOW,
) -> None:
    request = EventCreate(
        title=title,
        starts_at=starts_at,
        ends_at=starts_at + duration,
        event_type=event_type,
    )
    event = models.Event(
        **request.model_dump(),
        is_active=active,
        created_by=creator_id,
        created_at=NOW - timedelta(days=90),
    )
    db.add(event)
    await db.flush()
    if attendee_id is not None:
        db.add(
            models.EventAttendance(
                event_id=event.id,
                user_id=attendee_id,
                registered_at=registered_at,
                qr_secret=str(uuid.uuid4()),
                qr_hmac=str(uuid.uuid4()),
            )
        )
        await db.flush()


@pytest.mark.asyncio
async def test_attendance_compares_half_open_windows_and_projects_event_date(
    db_session, user_factory
):
    user = await user_factory()
    other = await user_factory()
    for days, attended in [
        (30, True),
        (15, False),
        (1, False),
        (60, True),
        (45, True),
        (31, False),
    ]:
        await add_event(
            db_session,
            user.id,
            title=f"Event {days}",
            starts_at=NOW - timedelta(days=days),
            attendee_id=user.id if attended else other.id,
        )
    for title, starts_at, active in [
        ("Starts now", NOW, True),
        ("Too old", NOW - timedelta(days=61), True),
        ("Inactive", NOW - timedelta(days=2), False),
    ]:
        await add_event(
            db_session,
            user.id,
            title=title,
            starts_at=starts_at,
            attendee_id=user.id,
            active=active,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result == {
        "percent": 33.33,
        "present": 1,
        "total": 3,
        "trend": -33.33,
        "period_key": "30d",
        "recent": [
            {
                "date": "2026-08-31T12:00:00+00:00",
                "status": "present",
                "course": "Event 30",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("have_events", [False, True])
async def test_attendance_without_registrations_reports_all_zero_counters(
    db_session, user_factory, have_events
):
    user = await user_factory()
    if have_events:
        for days in (1, 31):
            await add_event(
                db_session,
                user.id,
                title=f"Available {days}",
                starts_at=NOW - timedelta(days=days),
            )
    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result == {
        "percent": 0.0,
        "present": 0,
        "total": int(have_events),
        "trend": 0.0,
        "period_key": "30d",
        "recent": [],
    }


@pytest.mark.asyncio
async def test_participation_aggregates_fractional_hours_and_previous_event_count(
    db_session, user_factory
):
    user = await user_factory()
    for title, days, duration, event_type in [
        ("Short session", 1, timedelta(minutes=37), "workshop"),
        ("Hackathon", 2, timedelta(hours=24), "hackathon"),
    ]:
        await add_event(
            db_session,
            user.id,
            title=title,
            starts_at=NOW - timedelta(days=days),
            attendee_id=user.id,
            duration=duration,
            event_type=event_type,
        )
    for days in (31, 40, 60):
        await add_event(
            db_session,
            user.id,
            title=f"Previous {days}",
            starts_at=NOW - timedelta(days=days),
            attendee_id=user.id,
        )

    result = await UserAnalyticsService(db_session).get_participation_stats(
        user_id=user.id, period_days=30, period_key=" MONTH ", skip_cache=True
    )
    assert result == {
        "events": 2,
        "hours": 24.62,
        "groups": 2,
        "trend": -1,
        "period_key": "month",
        "recent": [
            {
                "title": "Short session",
                "date": "2026-09-29T12:00:00+00:00",
                "role": "workshop",
            },
            {
                "title": "Hackathon",
                "date": "2026-09-28T12:00:00+00:00",
                "role": "hackathon",
            },
        ],
    }


@pytest.mark.asyncio
async def test_participation_counts_all_events_but_limits_recent_rows_to_five(
    db_session, user_factory
):
    user = await user_factory()
    for days in range(1, 8):
        await add_event(
            db_session,
            user.id,
            title=f"Workshop {days}",
            starts_at=NOW - timedelta(days=days),
            attendee_id=user.id,
            event_type=None if days == 1 else "workshop",
        )
    result = await UserAnalyticsService(db_session).get_participation_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )
    assert result == {
        "events": 7,
        "hours": 7.0,
        "groups": 1,
        "trend": 7,
        "period_key": "30d",
        "recent": [
            {
                "title": f"Workshop {days}",
                "date": (NOW - timedelta(days=days)).isoformat(),
                "role": None if days == 1 else "workshop",
            }
            for days in range(1, 6)
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["attendance", "participation"])
async def test_activity_cache_is_scoped_to_user_and_period_and_can_be_bypassed(
    db_session, user_factory, kind
):
    user = await user_factory()
    other = await user_factory()
    service = UserAnalyticsService(db_session)
    get_stats = getattr(service, f"get_{kind}_stats")
    cache = MemoryCache()
    counter = "present" if kind == "attendance" else "events"
    first = await get_stats(user_id=user.id, period_days=7, cache=cache)
    assert first[counter] == 0
    assert first["period_key"] == "7d"
    await add_event(
        db_session,
        user.id,
        title="New registration",
        starts_at=NOW - timedelta(days=1),
        attendee_id=user.id,
    )
    assert (await get_stats(user_id=user.id, period_days=7, cache=cache)) == first
    fresh = await get_stats(
        user_id=user.id, period_days=7, cache=cache, skip_cache=True
    )
    assert fresh[counter] == 1
    assert (await get_stats(user_id=user.id, period_days=7, cache=cache)) == first
    named = await get_stats(
        user_id=user.id, period_days=7, period_key=" WEEK ", cache=cache
    )
    assert named[counter] == 1
    assert named["period_key"] == "week"
    other_result = await get_stats(
        user_id=other.id, period_days=7, period_key="week", cache=cache
    )
    assert other_result[counter] == 0
    await invalidate_user_stats_cache(user_ids=user.id, period_keys=["7d"], cache=cache)
    assert (await get_stats(user_id=user.id, period_days=7, cache=cache))[counter] == 1
