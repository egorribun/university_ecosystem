"""Persisted activity windows and cache behavior through the public service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.core.config import settings
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
    monkeypatch.setattr(settings, "campus_timezone", "UTC")


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
        "streak_days": 0,
        "daily": [
            {"date": "2026-08-31", "registered": 1, "total": 1},
            {"date": "2026-09-15", "registered": 0, "total": 1},
            {"date": "2026-09-29", "registered": 0, "total": 1},
        ],
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
        "streak_days": 0,
        "daily": (
            [{"date": "2026-09-29", "registered": 0, "total": 1}]
            if have_events
            else []
        ),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("campus_timezone", "expected"),
    [
        (
            "UTC",
            [
                {"date": "2026-09-28", "registered": 1, "total": 2},
                {"date": "2026-09-29", "registered": 0, "total": 1},
            ],
        ),
        (
            "Europe/Moscow",
            [
                {"date": "2026-09-28", "registered": 1, "total": 1},
                {"date": "2026-09-29", "registered": 0, "total": 2},
            ],
        ),
    ],
)
async def test_attendance_daily_counts_complete_population_in_campus_dates(
    db_session, user_factory, monkeypatch, campus_timezone, expected
):
    monkeypatch.setattr(settings, "campus_timezone", campus_timezone)
    user = await user_factory()
    other = await user_factory()
    for title, starts_at, attendee_id, active in [
        ("Registered", datetime(2026, 9, 28, 20, 30, tzinfo=UTC), user.id, True),
        ("Other user", datetime(2026, 9, 28, 21, 30, tzinfo=UTC), other.id, True),
        ("No registration", datetime(2026, 9, 29, 12, tzinfo=UTC), None, True),
        ("Inactive", datetime(2026, 9, 29, 13, tzinfo=UTC), user.id, False),
        ("Starts now", NOW, user.id, True),
        ("Previous window", NOW - timedelta(days=31), user.id, True),
    ]:
        await add_event(
            db_session,
            user.id,
            title=title,
            starts_at=starts_at,
            attendee_id=attendee_id,
            active=active,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result.get("daily") == expected
    assert result["present"] == 1
    assert result["total"] == 3
    assert result["percent"] == 33.33
    assert len(result["recent"]) == 1


@pytest.mark.asyncio
async def test_attendance_daily_is_not_limited_by_recent_registration_cap(
    db_session, user_factory, monkeypatch
):
    monkeypatch.setattr(settings, "campus_timezone", "UTC")
    user = await user_factory()
    for days in range(1, 8):
        for registered in (False, True):
            await add_event(
                db_session,
                user.id,
                title=f"Day {days} registration {registered}",
                starts_at=NOW - timedelta(days=days),
                attendee_id=user.id if registered else None,
            )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result.get("daily") == [
        {
            "date": (NOW - timedelta(days=days)).date().isoformat(),
            "registered": 1,
            "total": 2,
        }
        for days in range(7, 0, -1)
    ]
    assert len(result["recent"]) == 5
    assert result["present"] == 7
    assert result["total"] == 14
    assert result["percent"] == 50.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("day_offsets", "expected"),
    [
        ([], 0),
        ([0, 1, 2], 3),
        ([1, 2, 3], 3),
        ([0, 0, 1, 1, 2], 3),
        ([0, 2, 3], 1),
        ([1, 3, 4], 1),
        ([2, 3, 4], 0),
    ],
)
async def test_attendance_streak_counts_unique_current_consecutive_event_days(
    db_session, user_factory, day_offsets, expected
):
    user = await user_factory()
    for index, days in enumerate(day_offsets):
        await add_event(
            db_session,
            user.id,
            title=f"Registration {index}",
            starts_at=NOW - timedelta(days=days, hours=1),
            attendee_id=user.id,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result.get("streak_days") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("period_days", [30, 90, 180])
async def test_attendance_streak_is_independent_of_period_and_recent_cap(
    db_session, user_factory, period_days
):
    user = await user_factory()
    for days in range(36):
        await add_event(
            db_session,
            user.id,
            title=f"Consecutive event {days}",
            starts_at=NOW - timedelta(days=days, hours=1),
            attendee_id=user.id,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=period_days, skip_cache=True
    )

    assert result.get("streak_days") == 36
    assert len(result["recent"]) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("campus_timezone", "expected"), [("UTC", 1), ("Europe/Moscow", 2)]
)
async def test_attendance_streak_uses_campus_event_dates(
    db_session, user_factory, monkeypatch, campus_timezone, expected
):
    monkeypatch.setattr(settings, "campus_timezone", campus_timezone)
    user = await user_factory()
    for hour in (20, 21):
        await add_event(
            db_session,
            user.id,
            title=f"Midnight boundary {hour}",
            starts_at=datetime(2026, 9, 29, hour, 30, tzinfo=UTC),
            attendee_id=user.id,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result.get("streak_days") == expected


@pytest.mark.asyncio
async def test_attendance_streak_excludes_inactive_future_and_other_user_events(
    db_session, user_factory
):
    user = await user_factory()
    other = await user_factory()
    for title, starts_at, attendee_id, active in [
        ("Today", NOW - timedelta(hours=1), user.id, True),
        ("Inactive yesterday", NOW - timedelta(days=1), user.id, False),
        ("Other yesterday", NOW - timedelta(days=1), other.id, True),
        ("Before gap", NOW - timedelta(days=2), user.id, True),
        ("Starts now", NOW, user.id, True),
        ("Future", NOW + timedelta(days=1), user.id, True),
    ]:
        await add_event(
            db_session,
            user.id,
            title=title,
            starts_at=starts_at,
            attendee_id=attendee_id,
            active=active,
        )

    result = await UserAnalyticsService(db_session).get_attendance_stats(
        user_id=user.id, period_days=30, skip_cache=True
    )

    assert result.get("streak_days") == 1
