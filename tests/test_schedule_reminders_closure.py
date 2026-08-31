from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.notifications import schedule_reminders as reminders


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
        _lesson(id="s1", group_id="g1"),
        _lesson(id="s2", group_id="g1"),
        _lesson(id="s3", group_id="g2"),
    ]

    def payload(schedule):
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
    assert create.await_args.kwargs["tag"] == "tag-s2"
    assert create.await_args.kwargs["topic"] == "schedule.changed"


@pytest.mark.asyncio
async def test_generate_reminders_no_users_and_no_dedupe_query(monkeypatch):
    schedule = _lesson(id="s1", group_id="g1")
    monkeypatch.setattr(
        reminders,
        "build_schedule_reminder_message",
        lambda _schedule: ("", "", "", {}, {}, {}, ""),
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
    db = _Db([_ScalarResult(schedules=[_lesson()])])
    assert await reminders.generate_schedule_reminders(db) == 0
