from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.events import NotificationsRequested
from app.models import Group, Notification, Schedule
from app.models.domain_events import StoredEvent
from app.services.notifications import (
    delivery as notifications_delivery,
)
from app.services.notifications import (
    schedule_reminders as reminders,
)


def _lesson(**overrides):
    values = {
        "id": "lesson-1",
        "start_time": dt.datetime(2026, 7, 23, 10, 0, tzinfo=dt.UTC),
        "lesson_type": "seminar",
        "subject": "Mathematics",
        "group": SimpleNamespace(name="G-1"),
        "group_id": "group-1",
        "teacher": "Teacher",
        "room": "101",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _due_lesson(*, minutes: int = 2, **overrides):
    zone = ZoneInfo(reminders.settings.campus_timezone)
    start_local = (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes)).astimezone(
        zone
    )
    reference_date = dt.date(1970, 1, 5) + dt.timedelta(days=start_local.weekday())
    reference_start = dt.datetime.combine(reference_date, start_local.time()).replace(
        tzinfo=dt.UTC
    )
    values = {
        "weekday": start_local.strftime("%A").lower(),
        "parity": "odd" if start_local.isocalendar().week % 2 else "even",
        "start_time": reference_start,
    }
    values.update(overrides)
    return _lesson(**values)


def test_build_reminder_default_template_cache_and_room_prefix(monkeypatch):
    monkeypatch.setattr(
        reminders, "render_notification_template", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        reminders, "translate_lesson_type", lambda *args, **kwargs: None
    )
    result = reminders.build_schedule_reminder_message(
        _lesson(subject=None, teacher=None, room="Room 101"), locale="en"
    )
    title, body, tag, payload, title_translations, body_translations, dedupe = result
    assert title and body and tag and dedupe == tag
    assert "seminar" in body
    assert payload["room"] == "Room 101"
    assert set(title_translations) == reminders.SUPPORTED_LOCALES
    assert set(body_translations) == reminders.SUPPORTED_LOCALES


def test_build_reminder_template_fallbacks_no_details_and_legacy_dedupe(monkeypatch):
    monkeypatch.setattr(
        reminders,
        "render_notification_template",
        lambda *args, **kwargs: {
            "title": "",
            "body": "",
            "tag": "",
            "data": ["not-a-mapping"],
            "dedupe_key": "legacy-key",
        },
    )
    monkeypatch.setattr(
        reminders, "translate_lesson_type", lambda *args, **kwargs: None
    )
    result = reminders.build_schedule_reminder_message(
        _lesson(lesson_type=None, subject=None, teacher=None, room=None), locale=None
    )
    assert result[1]
    assert result[3]["lessonId"] == "lesson-1"
    assert result[6] == "legacy-key"


def test_build_reminder_can_omit_localized_title(monkeypatch):
    original_translate = reminders.translate

    def translate(key, *, locale=None, **kwargs):
        if locale == "ru" and key.startswith("notifications.schedule.reminder.title"):
            return ""
        return original_translate(key, locale=locale, **kwargs)

    monkeypatch.setattr(reminders, "translate", translate)
    monkeypatch.setattr(
        reminders, "render_notification_template", lambda *args, **kwargs: None
    )
    result = reminders.build_schedule_reminder_message(
        _lesson(subject=None), locale="en"
    )
    assert result[4]["en"]
    assert "ru" not in result[4]


class _ScalarResult:
    def __init__(self, rows=(), schedules=()):
        self.rows = list(rows)
        self.schedules = list(schedules)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self.schedules))

    def __iter__(self):
        return iter(self.rows)


class _Db:
    def __init__(self, results):
        self.results = list(results)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_generate_reminders_deduplicates_and_skips_invalid_rows(monkeypatch):
    schedules = [
        _due_lesson(id="s1", group_id="g1"),
        _due_lesson(id="s2", group_id="g1"),
        _due_lesson(id="s3", group_id="g2"),
    ]

    def payload(schedule, *, occurrence_at):
        assert occurrence_at.tzinfo is not None
        return (
            f"title-{schedule.id}",
            "body",
            f"tag-{schedule.id}",
            {"lessonId": schedule.id},
            {"en": f"title-{schedule.id}"},
            {"en": "body"},
            f"key-{schedule.id}",
        )

    monkeypatch.setattr(reminders, "build_schedule_reminder_message", payload)
    create = AsyncMock(return_value=2)
    monkeypatch.setattr(reminders, "create_notifications_for_users", create)
    db = _Db(
        [
            _ScalarResult(schedules=schedules),
            _ScalarResult(rows=[("u1", "g1"), (None, "g1"), ("u2", None)]),
            _ScalarResult(rows=[(None, "key-s1"), ("u1", None), ("u1", "key-s1")]),
        ]
    )
    created = await reminders.generate_schedule_reminders(db)
    assert created == 2
    assert create.await_count == 1
    assert create.await_args.kwargs["user_ids"] == ["u1"]
    assert create.await_args.kwargs["title"] == "title-s2"
    assert create.await_args.kwargs["body"] == "body"
    assert create.await_args.kwargs["title_translations"] == {"en": "title-s2"}
    assert create.await_args.kwargs["body_translations"] == {"en": "body"}
    assert create.await_args.kwargs["tag"] == "tag-s2"
    assert create.await_args.kwargs["actions"] == [
        {"action": "open-schedule", "title": "Open schedule", "url": "/schedule"}
    ]
    assert create.await_args.kwargs["payload_data"] == {"lessonId": "s2"}
    assert create.await_args.kwargs["topic"] == "schedule.changed"
    assert create.await_args.kwargs["user_filter"] is reminders.only_active_users


@pytest.mark.asyncio
async def test_generate_reminders_no_users_and_no_dedupe_query(monkeypatch):
    schedule = _due_lesson(id="s1", group_id="g1")
    monkeypatch.setattr(
        reminders,
        "build_schedule_reminder_message",
        lambda _schedule, *, occurrence_at: ("", "", "", {}, {}, {}, ""),
    )
    db = _Db(
        [
            _ScalarResult(schedules=[schedule]),
            _ScalarResult(rows=[(None, None)]),
        ]
    )
    assert await reminders.generate_schedule_reminders(db) == 0

    db = _Db([_ScalarResult(schedules=[schedule]), _ScalarResult(rows=[("u1", "g1")])])
    create = AsyncMock(return_value=1)
    monkeypatch.setattr(reminders, "create_notifications_for_users", create)
    assert await reminders.generate_schedule_reminders(db) == 1
    assert len(db.queries) == 2


@pytest.mark.asyncio
async def test_generate_reminders_returns_zero_when_schedule_window_is_empty():
    db = _Db([_ScalarResult(schedules=[])])

    assert await reminders.generate_schedule_reminders(db) == 0


@pytest.mark.asyncio
async def test_generate_reminders_defensive_empty_group_ids(monkeypatch):
    class _NoKeysDict(dict):
        def __missing__(self, key):
            value = []
            self[key] = value
            return value

        def keys(self):
            return ()

    monkeypatch.setattr(
        reminders, "defaultdict", lambda *_args, **_kwargs: _NoKeysDict()
    )
    db = _Db([_ScalarResult(schedules=[_due_lesson()])])
    assert await reminders.generate_schedule_reminders(db) == 0


def test_schedule_occurrence_uses_campus_date_wall_time_and_iso_week_parity():
    zone = ZoneInfo("Europe/Istanbul")
    now_utc = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)
    schedule = _lesson(
        weekday="monday",
        parity="even",
        start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
    )

    occurrence = reminders._schedule_occurrence_in_window(
        schedule,
        now_utc=now_utc,
        window_end_utc=now_utc + dt.timedelta(minutes=10),
        campus_timezone=zone,
    )

    assert occurrence is not None
    assert occurrence == dt.datetime(2026, 1, 5, 3, 0, tzinfo=zone)
    assert occurrence.astimezone(dt.UTC) == dt.datetime(2026, 1, 5, 0, 0, tzinfo=dt.UTC)
    assert (
        reminders._schedule_occurrence_in_window(
            _lesson(**{**vars(schedule), "parity": "odd"}),
            now_utc=now_utc,
            window_end_utc=now_utc + dt.timedelta(minutes=10),
            campus_timezone=zone,
        )
        is None
    )
    assert (
        reminders._schedule_occurrence_in_window(
            _lesson(**{**vars(schedule), "weekday": "sunday"}),
            now_utc=now_utc,
            window_end_utc=now_utc + dt.timedelta(minutes=10),
            campus_timezone=zone,
        )
        is None
    )
    assert (
        reminders._schedule_occurrence_in_window(
            _lesson(
                weekday="monday",
                parity="even",
                start_time=dt.datetime(1970, 1, 5, 3, 30, tzinfo=dt.UTC),
            ),
            now_utc=now_utc,
            window_end_utc=now_utc + dt.timedelta(minutes=10),
            campus_timezone=zone,
        )
        is None
    )


def test_schedule_occurrence_skips_dst_gap_and_uses_first_ambiguous_fold():
    zone = ZoneInfo("America/New_York")
    assert (
        reminders._resolve_schedule_occurrence(
            _lesson(start_time=None), dt.date(2026, 3, 8), zone
        )
        is None
    )
    nonexistent_now = dt.datetime(2026, 3, 8, 6, 25, tzinfo=dt.UTC)
    nonexistent = _lesson(
        weekday="sunday",
        start_time=dt.datetime(1970, 1, 4, 2, 30, tzinfo=dt.UTC),
    )
    assert (
        reminders._schedule_occurrence_in_window(
            nonexistent,
            now_utc=nonexistent_now,
            window_end_utc=nonexistent_now + dt.timedelta(minutes=80),
            campus_timezone=zone,
        )
        is None
    )

    ambiguous_now = dt.datetime(2026, 11, 1, 5, 25, tzinfo=dt.UTC)
    ambiguous = _lesson(
        weekday="sunday",
        start_time=dt.datetime(1970, 1, 4, 1, 30, tzinfo=dt.UTC),
    )
    occurrence = reminders._schedule_occurrence_in_window(
        ambiguous,
        now_utc=ambiguous_now,
        window_end_utc=ambiguous_now + dt.timedelta(minutes=10),
        campus_timezone=zone,
    )

    assert occurrence is not None
    assert occurrence == dt.datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    assert occurrence.astimezone(dt.UTC) == dt.datetime(
        2026, 11, 1, 5, 30, tzinfo=dt.UTC
    )


def test_build_schedule_reminder_formats_resolved_occurrence_in_campus_timezone(
    monkeypatch,
):
    monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")
    monkeypatch.setattr(
        reminders, "render_notification_template", lambda *_args, **_kwargs: None
    )
    occurrence = dt.datetime(2026, 1, 5, 0, 0, tzinfo=dt.UTC)

    result = reminders.build_schedule_reminder_message(
        _lesson(), occurrence_at=occurrence
    )

    assert result[3]["startText"] == "05.01 · 03:00"
    assert result[3]["startsAt"] == "2026-01-05T00:00:00+00:00"
    assert "05.01 · 03:00" in result[1]


@pytest.mark.asyncio
async def test_generate_reminders_resolves_reference_week_rows_to_due_campus_occurrence(
    db_session, user_factory, monkeypatch
):
    fixed_now = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)

    class _FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    clock = SimpleNamespace(**vars(dt))
    clock.datetime = _FixedDateTime
    monkeypatch.setattr(reminders, "dt", clock)
    monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")

    group = Group(name="Reference-week reminder")
    db_session.add(group)
    await db_session.flush()
    user = await user_factory(group_id=group.id)
    user_id = user.id
    db_session.add_all(
        [
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Matching reference week",
                weekday="monday",
                parity="even",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong parity",
                weekday="monday",
                parity="odd",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong weekday",
                weekday="tuesday",
                parity="both",
                start_time=dt.datetime(1970, 1, 6, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 6, 4, 0, tzinfo=dt.UTC),
            ),
        ]
    )
    await db_session.commit()
    create = AsyncMock(return_value=1)
    monkeypatch.setattr(reminders, "create_notifications_for_users", create)

    created = await reminders.generate_schedule_reminders(db_session, window_minutes=10)

    assert created == 1
    assert create.await_count == 1
    assert create.await_args.kwargs["user_ids"] == [user_id]
    assert create.await_args.kwargs["payload_data"]["startText"] == ("05.01 · 03:00")
    assert create.await_args.kwargs["payload_data"]["startsAt"] == (
        "2026-01-05T03:00:00+03:00"
    )


def test_schedule_occurrence_window_can_cross_campus_midnight():
    zone = ZoneInfo("Europe/Istanbul")
    now_utc = dt.datetime(2026, 1, 4, 20, 59, tzinfo=dt.UTC)
    schedule = _lesson(
        weekday="monday",
        parity="even",
        start_time=dt.datetime(1970, 1, 5, 0, 5, tzinfo=dt.UTC),
    )

    occurrence = reminders._schedule_occurrence_in_window(
        schedule,
        now_utc=now_utc,
        window_end_utc=now_utc + dt.timedelta(minutes=10),
        campus_timezone=zone,
    )

    assert occurrence is not None
    assert occurrence == dt.datetime(2026, 1, 5, 0, 5, tzinfo=zone)


@pytest.mark.asyncio
async def test_reference_week_reminder_persists_once_for_real_campus_occurrence(
    db_session, user_factory, monkeypatch
):
    fixed_now = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)

    class _FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    clock = SimpleNamespace(**vars(dt))
    clock.datetime = _FixedDateTime
    monkeypatch.setattr(reminders, "dt", clock)
    monkeypatch.setattr(notifications_delivery, "dt", clock)
    monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)

    group = Group(name="Reference-week persistence")
    db_session.add(group)
    await db_session.flush()
    user = await user_factory(group_id=group.id)
    user_id = user.id
    db_session.add_all(
        [
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Matching local Monday",
                weekday="monday",
                parity="even",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong local parity",
                weekday="monday",
                parity="odd",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong local weekday",
                weekday="tuesday",
                parity="both",
                start_time=dt.datetime(1970, 1, 6, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 6, 4, 0, tzinfo=dt.UTC),
            ),
        ]
    )
    await db_session.commit()

    created = await reminders.generate_schedule_reminders(db_session, window_minutes=10)
    await db_session.commit()
    assert created == 1

    reader_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with reader_factory() as reader:
        notifications = (
            (
                await reader.execute(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.type == "schedule.reminder",
                        Notification.url == "/schedule",
                    )
                )
            )
            .scalars()
            .all()
        )
        outbox_events = (
            (
                await reader.execute(
                    select(StoredEvent).where(
                        StoredEvent.event_type == NotificationsRequested.EVENT_TYPE,
                        StoredEvent.aggregate_type == "NotificationBatch",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(notifications) == 1
    assert "05.01 · 03:00" in notifications[0].body
    assert len(outbox_events) == 1
    assert outbox_events[0].payload["notification_ids"] == [str(notifications[0].id)]

    assert (
        await reminders.generate_schedule_reminders(db_session, window_minutes=10) == 0
    )
    await db_session.commit()
