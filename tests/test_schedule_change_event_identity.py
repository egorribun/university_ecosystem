"""Distinct schedule mutations notify once per persisted event, including retries."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import models
from app.core.database import async_session
from app.core.events import (
    EventBus,
    NotificationsRequested,
    ScheduleDeleted,
    ScheduleUpdated,
)
from app.models.domain_events import StoredEvent
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.event_handlers import handle_schedule_changed
from app.services.schedule_optimizer import ScheduleOptimizerService
from app.services.schedule_service import ScheduleService
from app.workers import outbox


@pytest.fixture
async def schedule_notification_case(db_session, user_factory, monkeypatch):
    group = models.Group(name="NOTIFICATION-EVENT-IDENTITY")
    db_session.add(group)
    await db_session.commit()
    user = await user_factory(group_id=group.id)
    service = ScheduleService(uow_from_session(db_session), ScheduleOptimizerService())
    schedule = await service.create_schedule(
        schemas.ScheduleCreate(
            group_id=group.id,
            subject="Synthetic seminar",
            room="101",
            weekday="monday",
            start_time=datetime(2026, 9, 28, 9, tzinfo=UTC),
            end_time=datetime(2026, 9, 28, 10, tzinfo=UTC),
        ),
        locale="en",
    )
    # Exercise the real event bus and handler without unrelated subscribers or
    # external services. The producer, outbox reconstruction and DB are real.
    bus = EventBus()
    bus.subscribe(ScheduleUpdated.EVENT_TYPE, handle_schedule_changed)
    bus.subscribe(ScheduleDeleted.EVENT_TYPE, handle_schedule_changed)
    monkeypatch.setattr(outbox, "event_bus", bus)
    return service, schedule.id, user.id, outbox.OutboxWorker()


async def _latest_event(db, schedule_id, event_type):
    event = (
        await db.execute(
            select(StoredEvent)
            .where(
                StoredEvent.aggregate_id == str(schedule_id),
                StoredEvent.event_type == event_type,
            )
            .order_by(StoredEvent.sequence_number.desc())
            .limit(1)
        )
    ).scalar_one()
    # Preserve the loaded row while ending this read transaction before the
    # handler writes through its own session, as it does in production.
    db.expunge(event)
    await db.rollback()
    return event


async def _committed_notifications(user_id):
    async with async_session() as observer:
        rows = await observer.execute(
            select(models.Notification)
            .where(
                models.Notification.user_id == user_id,
                models.Notification.type == "schedule.change",
            )
            .order_by(models.Notification.created_at, models.Notification.id)
        )
        notifications = list(rows.scalars())
        requests = list(
            (
                await observer.execute(
                    select(StoredEvent).where(
                        StoredEvent.event_type == NotificationsRequested.EVENT_TYPE
                    )
                )
            ).scalars()
        )
        return notifications, requests


async def test_repeated_transition_notifies_for_each_committed_event(
    db_session, schedule_notification_case
):
    service, schedule_id, user_id, worker = schedule_notification_case
    events = []
    for count, room in enumerate(("202", "101", "202"), start=1):
        changed = await service.update_schedule(
            schedule_id, schemas.ScheduleUpdate(room=room)
        )
        assert changed.room == room
        event = await _latest_event(db_session, schedule_id, ScheduleUpdated.EVENT_TYPE)
        events.append(event)
        await worker._dispatch_event(event)
        notifications, requests = await _committed_notifications(user_id)
        assert len(notifications) == count
        assert len(requests) == count
        assert f"room {room}" in notifications[-1].body_en

    assert len({event.id for event in events}) == 3
    assert events[0].payload == events[2].payload
    assert len({item.dedupe_key for item in notifications}) == 3
    # Reconstructing the same stored rows again must preserve their identity.
    for event in events:
        await worker._dispatch_event(event)
    notifications, requests = await _committed_notifications(user_id)
    assert len(notifications) == len(requests) == 3


async def test_replayed_cancellation_keeps_one_notification_and_push_request(
    db_session, schedule_notification_case
):
    service, schedule_id, user_id, worker = schedule_notification_case
    assert await service.delete_schedule(schedule_id)
    event = await _latest_event(db_session, schedule_id, ScheduleDeleted.EVENT_TYPE)
    await worker._dispatch_event(event)
    await worker._dispatch_event(event)
    notifications, requests = await _committed_notifications(user_id)
    assert len(notifications) == len(requests) == 1
    assert "The class was cancelled" in notifications[0].body_en
