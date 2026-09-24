"""Lesson changes notify the affected groups once (topic ``schedule.changed``)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app import models
from app.core.events import ScheduleDeleted, ScheduleUpdated
from app.services.event_handlers import handle_schedule_changed
from app.services.notifications.schedule_changes import (
    SCHEDULE_CHANGE_TOPIC,
    is_significant_change,
    notify_about_schedule_change,
)


def _state(group_id: uuid.UUID, **overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "group_id": str(group_id),
        "subject": "Physics",
        "teacher": "Dr. Curie",
        "room": "101",
        "weekday": "monday",
        "start_time": "2026-09-28T09:00:00+00:00",
        "end_time": "2026-09-28T10:30:00+00:00",
        "parity": "both",
        "lesson_type": None,
    }
    state.update(overrides)
    return state


async def _group(db_session, name: str) -> models.Group:
    group = models.Group(name=name)
    db_session.add(group)
    await db_session.flush()
    return group


async def _notifications(db_session) -> list[models.Notification]:
    rows = await db_session.execute(select(models.Notification))
    return list(rows.scalars())


def test_significance_rules() -> None:
    group_id = uuid.uuid4()
    assert is_significant_change(_state(group_id), _state(group_id)) is False
    assert is_significant_change(_state(group_id), _state(group_id, room="202"))
    assert is_significant_change(_state(group_id), None) is True
    assert is_significant_change({}, None) is False


@pytest.mark.asyncio
async def test_change_notifies_active_group_members_once(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "CHANGE-1")
    other = await _group(db_session, "CHANGE-OTHER")
    first = await user_factory(group_id=group.id)
    second = await user_factory(group_id=group.id)
    await user_factory(group_id=group.id, is_active=False)
    await user_factory(group_id=other.id)
    schedule_id = uuid.uuid4()
    previous, current = _state(group.id), _state(group.id, room="202")

    with patch(
        "app.services.notifications.delivery._is_push_configured", return_value=False
    ):
        created = await notify_about_schedule_change(
            db_session, schedule_id=schedule_id, previous=previous, current=current
        )
        repeated = await notify_about_schedule_change(
            db_session, schedule_id=schedule_id, previous=previous, current=current
        )

    assert created == 2
    assert repeated == 0
    rows = await _notifications(db_session)
    assert {row.user_id for row in rows} == {first.id, second.id}
    row = rows[0]
    assert row.type == "schedule.change"
    assert row.url == "/schedule"
    assert row.dedupe_key.startswith(f"schedule-change:{schedule_id}:")
    assert row.title == "Изменение пары: Physics"
    assert row.title_en == "Class change: Physics"
    assert "Пара перенесена или изменена" in (row.body or "")
    assert "ауд. 202" in (row.body or "")
    assert "The class was rescheduled or changed" in (row.body_en or "")
    assert "room 202" in (row.body_en or "")


@pytest.mark.asyncio
async def test_cancellation_and_group_move_reach_every_affected_group(
    db_session, user_factory
) -> None:
    before = await _group(db_session, "MOVE-FROM")
    after = await _group(db_session, "MOVE-TO")
    leaving = await user_factory(group_id=before.id)
    joining = await user_factory(group_id=after.id)

    with patch(
        "app.services.notifications.delivery._is_push_configured", return_value=False
    ):
        moved = await notify_about_schedule_change(
            db_session,
            schedule_id=uuid.uuid4(),
            previous=_state(before.id),
            current=_state(after.id),
        )
        cancelled = await notify_about_schedule_change(
            db_session,
            schedule_id=uuid.uuid4(),
            previous=_state(after.id),
            current=None,
        )
        unchanged = await notify_about_schedule_change(
            db_session,
            schedule_id=uuid.uuid4(),
            previous=_state(after.id),
            current=_state(after.id),
        )

    assert moved == 2
    assert cancelled == 1
    assert unchanged == 0
    rows = await _notifications(db_session)
    assert sorted(row.user_id for row in rows) == sorted(
        [leaving.id, joining.id, joining.id]
    )
    assert any("The class was cancelled" in (row.body_en or "") for row in rows)
    assert any("Пара отменена" in (row.body or "") for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected_current"),
    [
        (
            ScheduleUpdated(
                schedule_id="s-1",
                previous_state={"room": "101"},
                current_state={"room": "202"},
            ),
            {"room": "202"},
        ),
        (ScheduleDeleted(schedule_id="s-1", previous_state={"room": "101"}), None),
    ],
)
async def test_handler_forwards_snapshots(event, expected_current) -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.event_handlers.async_session", return_value=context),
        patch(
            "app.services.notifications.schedule_changes.notify_about_schedule_change",
            new=AsyncMock(return_value=1),
        ) as notify,
    ):
        await handle_schedule_changed(event)

    notify.assert_awaited_once_with(
        session,
        schedule_id="s-1",
        previous={"room": "101"},
        current=expected_current,
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        ScheduleUpdated(current_state={"room": "202"}),
        ScheduleUpdated(schedule_id="s-1", current_state={"room": "202"}),
    ],
)
async def test_handler_skips_legacy_events_without_a_snapshot(event) -> None:
    with (
        patch("app.services.event_handlers.async_session") as session_factory,
        patch(
            "app.services.notifications.schedule_changes.notify_about_schedule_change",
            new=AsyncMock(),
        ) as notify,
    ):
        await handle_schedule_changed(event)

    session_factory.assert_not_called()
    notify.assert_not_awaited()


def test_topic_is_the_canonical_schedule_topic() -> None:
    from app.core.notification_contract import CANONICAL_NOTIFICATION_TOPICS

    assert SCHEDULE_CHANGE_TOPIC == "schedule.changed"
    assert SCHEDULE_CHANGE_TOPIC in CANONICAL_NOTIFICATION_TOPICS


@pytest.mark.asyncio
async def test_changes_without_a_reachable_group_or_member_notify_nobody(
    db_session,
) -> None:
    empty_group = await _group(db_session, "NO-MEMBERS")
    unknown = {"subject": "Physics", "group_id": "not-a-uuid"}

    assert (
        await notify_about_schedule_change(
            db_session, schedule_id="s-1", previous=unknown, current=None
        )
        == 0
    )
    assert (
        await notify_about_schedule_change(
            db_session, schedule_id="s-2", previous={"subject": "Physics"}, current=None
        )
        == 0
    )
    assert (
        await notify_about_schedule_change(
            db_session,
            schedule_id="s-3",
            previous=_state(empty_group.id),
            current=None,
        )
        == 0
    )
    assert await _notifications(db_session) == []


@pytest.mark.asyncio
async def test_unparseable_times_and_unknown_weekdays_are_left_out(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "LOOSE-STATE")
    await user_factory(group_id=group.id)
    previous = _state(group.id)
    current = _state(
        group.id, weekday="funday", start_time="not-a-time", end_time=None, room="303"
    )

    with patch(
        "app.services.notifications.delivery._is_push_configured", return_value=False
    ):
        created = await notify_about_schedule_change(
            db_session, schedule_id="s-4", previous=previous, current=current
        )

    assert created == 1
    (row,) = await _notifications(db_session)
    assert "funday" not in (row.body_en or "")
    assert "not-a-time" not in (row.body_en or "")
    assert "room 303" in (row.body_en or "")


@pytest.mark.asyncio
async def test_start_only_time_is_rendered_without_a_range(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "START-ONLY")
    await user_factory(group_id=group.id)

    with patch(
        "app.services.notifications.delivery._is_push_configured", return_value=False
    ):
        await notify_about_schedule_change(
            db_session,
            schedule_id="s-5",
            previous=_state(group.id),
            current=_state(group.id, end_time=None),
        )

    (row,) = await _notifications(db_session)
    assert "09:00" in (row.body_en or "")
    assert "–" not in (row.body_en or "")


def _fingerprint(previous: object, current: object) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps({"previous": previous, "current": current}, sort_keys=True).encode()
    ).hexdigest()[:16]


async def _capture_delivery(db_session, *, previous, current, schedule_id):
    deliver = AsyncMock(return_value=1)
    with patch(
        "app.services.notifications.schedule_changes.create_notifications_for_users",
        deliver,
    ):
        created = await notify_about_schedule_change(
            db_session, schedule_id=schedule_id, previous=previous, current=current
        )
    assert created == 1
    deliver.assert_awaited_once()
    return deliver.await_args.kwargs


@pytest.mark.asyncio
async def test_delivery_carries_the_exact_localized_change(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "EXACT")
    member = await user_factory(group_id=group.id)
    schedule_id = uuid.uuid4()
    previous = _state(group.id)
    current = _state(group.id, room="202", weekday="Monday")

    kwargs = await _capture_delivery(
        db_session, previous=previous, current=current, schedule_id=schedule_id
    )

    ru_body = (
        "Пара перенесена или изменена\nПонедельник 09:00–10:30 · ауд. 202 · Dr. Curie"
    )
    en_body = "The class was rescheduled or changed\nMonday 09:00–10:30 · room 202 · Dr. Curie"
    assert kwargs == {
        # English is the default locale.
        "title": "Class change: Physics",
        "body": en_body,
        "title_translations": {
            "en": "Class change: Physics",
            "ru": "Изменение пары: Physics",
        },
        "body_translations": {"en": en_body, "ru": ru_body},
        "type": "schedule.change",
        "url": "/schedule",
        "tag": f"schedule-change:{schedule_id}",
        "dedupe_key": (
            f"schedule-change:{schedule_id}:{_fingerprint(previous, current)}"
        ),
        "payload_data": {
            "url": "/schedule",
            "category": "schedule",
            "subject": "Physics",
            "lessonId": str(schedule_id),
        },
        "user_ids": [member.id],
        "topic": "schedule.changed",
    }


@pytest.mark.asyncio
async def test_cancellation_describes_the_previous_lesson(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "EXACT-CANCEL")
    await user_factory(group_id=group.id)

    kwargs = await _capture_delivery(
        db_session, previous=_state(group.id), current=None, schedule_id="s-9"
    )

    assert kwargs["body_translations"]["en"] == (
        "The class was cancelled\nMonday 09:00–10:30 · room 101 · Dr. Curie"
    )
    assert (
        kwargs["dedupe_key"]
        == f"schedule-change:s-9:{_fingerprint(_state(group.id), None)}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("unusable", ["not-a-uuid", "", None])
async def test_an_unusable_previous_group_does_not_hide_the_current_one(
    db_session, user_factory, unusable
) -> None:
    group = await _group(db_session, f"FALLBACK-{unusable}")
    member = await user_factory(group_id=group.id)

    kwargs = await _capture_delivery(
        db_session,
        previous={**_state(group.id), "group_id": unusable},
        current=_state(group.id, room="404"),
        schedule_id="s-10",
    )

    assert kwargs["user_ids"] == [member.id]


@pytest.mark.asyncio
async def test_a_missing_weekday_is_left_out_of_the_details(
    db_session, user_factory
) -> None:
    group = await _group(db_session, "NO-WEEKDAY")
    await user_factory(group_id=group.id)

    kwargs = await _capture_delivery(
        db_session,
        previous=_state(group.id),
        current=_state(group.id, weekday=None),
        schedule_id="s-11",
    )

    assert kwargs["body_translations"]["en"] == (
        "The class was rescheduled or changed\n09:00–10:30 · room 101 · Dr. Curie"
    )
