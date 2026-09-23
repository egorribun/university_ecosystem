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
