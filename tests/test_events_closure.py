"""Focused closure tests for the domain event registry and bus."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

import app.core.events as events
from app.core.events import (
    AttachmentCleanupRequested,
    ChatDeleted,
    EventBus,
    EventCreated,
    EventEmitterMixin,
    EventRegistration,
    EventUpdated,
    GradeAssigned,
    GradeModified,
    MessageSent,
    MfaEnabled,
    NewsCreated,
    NewsUpdated,
    NotificationSent,
    NotificationsRequested,
    ScheduleCreated,
    ScheduleUpdated,
    UserCreated,
    UserDeleted,
    UserLoggedIn,
    UserUpdated,
)


def test_registry_snapshot_and_all_event_from_dict_variants() -> None:
    snapshot = events.get_registered_events()
    assert snapshot["UserCreated"] is UserCreated
    snapshot.pop("UserCreated")
    assert events.get_registered_events()["UserCreated"] is UserCreated

    cases = [
        (EventUpdated, {"event_id_entity": str(uuid4()), "title": "updated"}),
        (EventRegistration, {"event_id_entity": str(uuid4()), "user_id": str(uuid4())}),
        (NewsCreated, {"news_id": str(uuid4()), "title": "news"}),
        (NewsUpdated, {"news_id": str(uuid4()), "title": "updated"}),
        (
            AttachmentCleanupRequested,
            {"chat_id": str(uuid4()), "attachment_urls": ["a"]},
        ),
        (
            NotificationSent,
            {"notification_id": "notification", "notification_type": "push"},
        ),
        (NotificationsRequested, {"notification_ids": ["one"], "channel": "email"}),
        (EventCreated, {"event_id_entity": str(uuid4()), "organizer_id": str(uuid4())}),
        (MessageSent, {"message_id": str(uuid4()), "content_preview": "hello"}),
        (ChatDeleted, {"chat_id": str(uuid4()), "participant_id": str(uuid4())}),
        (MfaEnabled, {"user_id": str(uuid4()), "method": "totp"}),
        (UserDeleted, {"user_id": str(uuid4())}),
        (UserLoggedIn, {"user_id": str(uuid4()), "ip_address": "127.0.0.1"}),
        (UserUpdated, {"user_id": str(uuid4()), "updated_fields": ["email"]}),
    ]
    for event_class, payload in cases:
        payload["_schema_version"] = 2
        payload["unknown"] = "ignored"
        event = event_class.from_dict(payload)
        assert event.event_type == event_class.EVENT_TYPE


def test_schedule_and_grade_events_filter_schema_metadata() -> None:
    cases = [
        (ScheduleCreated, {"schedule_id": str(uuid4()), "subject": "Math"}),
        (ScheduleUpdated, {"schedule_id": str(uuid4()), "changes": {"room": "A"}}),
        (GradeAssigned, {"grade_id": str(uuid4()), "score": 95.0}),
        (GradeModified, {"grade_id": str(uuid4()), "new_score": 98.0}),
    ]
    for event_class, payload in cases:
        payload["_schema_version"] = 2
        payload["unknown"] = "ignored"
        event = event_class.from_dict(payload)
        assert event.event_type == event_class.EVENT_TYPE


def test_registry_accepts_class_without_event_type_without_alias() -> None:
    before = events.get_registered_events()

    class NoEventType:
        pass

    try:
        assert events.register_domain_event(NoEventType) is NoEventType
        assert events.get_registered_events()["NoEventType"] is NoEventType
        assert "NoEventType.EVENT_TYPE" not in events.get_registered_events()
    finally:
        events._EVENT_REGISTRY.clear()
        events._EVENT_REGISTRY.update(before)


def test_capture_domain_events_serializes_changed_and_tracked_emitters() -> None:
    class StoredEvent:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    class Entity(EventEmitterMixin):
        pass

    tracked = Entity()
    tracked.id = UUID("019c1468-f495-7980-9ad0-d8f31705df79")
    tracked._pending_domain_events = [
        UserCreated(user_id=uuid4(), email="user@example.com")
    ]
    unsafe = Entity()
    unsafe.id = object()
    unsafe._pending_domain_events = [UserDeleted(user_id=uuid4())]
    session = SimpleNamespace(
        new={tracked, unsafe},
        dirty=set(),
        deleted=set(),
        info={"_event_emitters": {tracked}},
    )

    with patch("app.models.domain_events.StoredEvent", StoredEvent):
        events.capture_domain_events(session, None)

    stored = session.info["_pending_stored_events"]
    assert len(stored) == 2
    assert {item.aggregate_id for item in stored} == {str(tracked.id), "unknown"}
    assert session.info["_event_emitters"] == set()
    assert tracked._pending_domain_events == []
    assert unsafe._pending_domain_events == []


def test_record_event_tracks_session_bound_emitters_and_empty_capture_is_safe() -> None:
    class Entity(EventEmitterMixin):
        pass

    session = SimpleNamespace(info={})
    entity = Entity()
    with patch("sqlalchemy.inspect", return_value=SimpleNamespace(session=session)):
        entity.record_event(UserCreated(email="tracked@example.com"))
    assert entity in session.info["_event_emitters"]

    empty_session = SimpleNamespace(new=set(), dirty=set(), deleted=set(), info={})
    events.capture_domain_events(empty_session, None)
    assert empty_session.info == {}


def test_register_event_listeners_registers_all_hooks() -> None:
    with patch("sqlalchemy.event.listen") as listen:
        import asyncio

        asyncio.run(events.register_event_listeners())
    assert listen.call_count == 3


def test_persist_and_commit_helpers_cover_empty_and_pending_states() -> None:
    pending = object()
    session = MagicMock()
    session.info = {"_pending_stored_events": [pending]}
    events._persist_captured_events(session, None)
    session.add_all.assert_called_once_with([pending])

    session.info = {}
    events._persist_captured_events(session, None)
    session.add_all.assert_called_once()

    with (
        patch.object(events, "capture_domain_events") as capture,
        patch.object(events, "_persist_captured_events") as persist,
    ):
        events.capture_on_commit(session)
    capture.assert_called_once_with(session, None)
    persist.assert_called_once_with(session, None)


@pytest.mark.asyncio
async def test_event_bus_timeout_middleware_exception_and_cancel_paths() -> None:
    event = UserCreated(email="user@example.com")
    bus = EventBus()

    await EventBus().publish(event)

    async def handler(_event: object) -> None:
        await asyncio.sleep(1)

    bus.subscribe(event.event_type, handler)

    async def pending_wait(tasks: set[asyncio.Task[object]], timeout: float):
        del timeout
        return set(), tasks

    with patch.object(events.asyncio, "wait", side_effect=pending_wait):
        await bus.publish(event)

    failing_bus = EventBus()

    async def failing_middleware(_event: object, _next: object) -> None:
        raise RuntimeError("middleware failed")

    failing_bus.add_middleware(failing_middleware)
    failing_bus.subscribe(event.event_type, handler)
    with pytest.raises(RuntimeError, match="middleware failed"):
        await failing_bus.publish(event)

    cancelled_bus = EventBus()
    cancelled_bus.subscribe(event.event_type, handler)
    with patch.object(events.asyncio, "wait", side_effect=asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await cancelled_bus.publish(event)

    bus.unsubscribe(event.event_type, handler)
    bus.unsubscribe(event.event_type, handler)
    bus.unsubscribe_all(handler)


@pytest.mark.asyncio
async def test_event_bus_successful_chain_and_handler_registry_lifecycle() -> None:
    event = UserCreated(email="success@example.com")
    bus = EventBus()

    async def successful_handler(_event: object) -> None:
        return None

    bus.subscribe(event.event_type, successful_handler)
    bus.subscribe_all(successful_handler)
    assert bus.get_handler_count(event.event_type) == 2
    assert bus.get_handler_count() == 2
    await bus.publish(event)

    bus.unsubscribe_all(successful_handler)
    bus.unsubscribe_all(successful_handler)
    bus.clear()
    assert bus.get_handler_count() == 0


@pytest.mark.asyncio
async def test_safe_handle_reports_dlq_failure() -> None:
    bus = EventBus()
    event = UserCreated(email="user@example.com")

    async def failing_handler(_event: object) -> None:
        raise RuntimeError("handler failed")

    dlq = MagicMock()
    dlq.add = AsyncMock(side_effect=RuntimeError("dlq failed"))
    bus.set_dlq(dlq)
    await bus._safe_handle(failing_handler, event)
    dlq.add.assert_awaited_once()

    no_dlq_bus = EventBus()
    await no_dlq_bus._safe_handle(failing_handler, event)
