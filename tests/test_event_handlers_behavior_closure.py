"""Behavior-level closure tests for domain-event handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.events import (
    AttachmentCleanupRequested,
    EventCreated,
    EventRegistration,
    MessageDeleted,
    MessageEdited,
    MessageSent,
    MfaEnabled,
    NewsCreated,
    NotificationSent,
    NotificationsRequested,
    UserCreated,
    UserLoggedIn,
)
from app.services import event_handlers


@pytest.mark.asyncio
async def test_simple_event_handlers_accept_normal_and_optional_payloads():
    await event_handlers.log_all_events(UserCreated(user_id=1, email="a@example.com"))
    await event_handlers.handle_user_created(UserCreated(user_id=1))
    await event_handlers.handle_user_logged_in(UserLoggedIn(user_id=1, ip_address=None))
    await event_handlers.handle_mfa_enabled(MfaEnabled(user_id=1, method="totp"))
    await event_handlers.handle_event_created(
        EventCreated(event_id_entity=2, organizer_id=3, title="Event")
    )
    await event_handlers.handle_event_registration(
        EventRegistration(event_id_entity=2, user_id=3)
    )
    await event_handlers.handle_notification_sent(
        NotificationSent(notification_id="n-1", user_id=3, notification_type="push")
    )


def _session(db: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


def _configure_message_rls_mock(db: AsyncMock, member_id) -> None:
    async def execute(statement, parameters=None):
        if "chat_participants" in str(statement):
            return SimpleNamespace(scalar_one_or_none=lambda: member_id)
        return SimpleNamespace()

    db.execute.side_effect = execute
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )


@pytest.mark.asyncio
async def test_event_and_news_embedding_handlers_cover_missing_and_success():
    missing_db = AsyncMock()
    missing_db.get.return_value = None
    with (
        patch.object(event_handlers, "async_session", lambda: _session(missing_db)),
        patch.object(event_handlers, "VectorService", return_value=AsyncMock()),
    ):
        await event_handlers.generate_event_embedding(
            EventCreated(event_id_entity=uuid4())
        )
    missing_db.commit.assert_not_awaited()

    db = AsyncMock()
    db_event = SimpleNamespace(
        title="Title",
        description=None,
        location="Room A",
        embedding=None,
    )
    db.get.return_value = db_event
    vector = MagicMock()
    vector.get_embedding = AsyncMock(return_value=[0.1, 0.2])
    vector.close = AsyncMock()
    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch.object(event_handlers, "VectorService", return_value=vector),
    ):
        await event_handlers.generate_event_embedding(
            EventCreated(event_id_entity=uuid4())
        )
    assert db_event.embedding == [0.1, 0.2]
    db.commit.assert_awaited_once()

    news_db = AsyncMock()
    db_news = SimpleNamespace(title="News", content="Body", embedding=None)
    news_db.get.return_value = db_news
    with (
        patch.object(event_handlers, "async_session", lambda: _session(news_db)),
        patch.object(event_handlers, "VectorService", return_value=vector),
    ):
        await event_handlers.generate_news_embedding(NewsCreated(news_id=uuid4()))
    assert db_news.embedding == [0.1, 0.2]
    news_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_handler_successfully_notifies_with_reply(monkeypatch):
    message_id = uuid4()
    chat_id = uuid4()
    reply_id = uuid4()
    sender_id = uuid4()
    message = SimpleNamespace(
        chat_id=chat_id,
        sender_id=sender_id,
        sender=None,
        reply_to_message_id=reply_id,
    )
    sender = SimpleNamespace(id=sender_id)
    reply = SimpleNamespace(id=reply_id)
    chat = SimpleNamespace(participants=[sender], chat_type="group", name="Study")
    db = AsyncMock()
    db.get.side_effect = [message, sender]
    _configure_message_rls_mock(db, sender_id)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=chat)
    repo.get_message_by_id = AsyncMock(return_value=reply)
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with (
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch(
            "app.services.chat.notification_service.ChatNotificationService"
        ) as service_class,
    ):
        service_class.return_value.notify_new_message = AsyncMock()
        await event_handlers.handle_message_sent(
            MessageSent(message_id=message_id, chat_id=chat_id)
        )

    assert message.sender is sender
    repo.get_message_by_id.assert_awaited_once_with(
        reply_id, user_id=sender_id, chat_id=chat_id
    )
    service_class.return_value.notify_new_message.assert_awaited_once_with(
        message=message,
        chat_participants=chat.participants,
        sender=sender,
        replied=reply,
        chat_type="group",
        chat_name="Study",
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_mutation_handlers_broadcast_committed_rows(monkeypatch):
    message_id = uuid4()
    chat_id = uuid4()
    edited_at = datetime.now(UTC)
    deleted_at = datetime.now(UTC)

    edited_message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        content="committed edit",
        edited_at=edited_at,
        deleted_at=None,
    )
    edit_db = AsyncMock()
    edit_db.get.return_value = edited_message
    _configure_message_rls_mock(edit_db, uuid4())
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(edit_db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        await event_handlers.handle_message_edited(
            MessageEdited(message_id=message_id, chat_id=chat_id)
        )

    broadcast.assert_awaited_once_with(
        chat_id,
        {
            "type": "message_edited",
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "content": "committed edit",
            "edited_at": edited_at.isoformat(),
        },
        propagate_nats_failure=True,
    )

    deleted_message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        content="",
        edited_at=edited_at,
        deleted_at=deleted_at,
    )
    delete_db = AsyncMock()
    delete_db.get.return_value = deleted_message
    _configure_message_rls_mock(delete_db, uuid4())
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(delete_db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        await event_handlers.handle_message_deleted(
            MessageDeleted(message_id=message_id, chat_id=chat_id)
        )

    broadcast.assert_awaited_once_with(
        chat_id,
        {
            "type": "message_deleted",
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "deleted_at": deleted_at.isoformat(),
        },
        propagate_nats_failure=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
@pytest.mark.parametrize("kind", ["sent", "edited", "deleted"])
async def test_message_handlers_set_rls_identity_before_reading_messages(
    monkeypatch, kind, dialect
):
    message_id = uuid4()
    chat_id = uuid4()
    member_id = uuid4()
    timestamp = datetime.now(UTC)
    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=member_id,
        sender=None,
        reply_to_message_id=None,
        content="committed message",
        edited_at=timestamp,
        deleted_at=timestamp if kind == "deleted" else None,
    )
    sender = SimpleNamespace(id=member_id)
    operations: list[str] = []

    class _MembershipResult:
        def scalar_one_or_none(self):
            return member_id

    async def execute(statement, parameters=None):
        sql = str(statement)
        if "chat_participants" in sql:
            operations.append("membership")
            return _MembershipResult()
        if "set_config('app.current_user_id'" in sql:
            operations.append("rls_identity")
            assert parameters == {"uid": str(member_id)}
            return SimpleNamespace()
        raise AssertionError("unexpected SQL in message event handler")

    async def get(model, identity):
        if model is event_handlers.models.Message:
            operations.append("message_read")
            assert identity == message_id
            return message
        if model is event_handlers.models.User:
            operations.append("sender_read")
            return sender
        raise AssertionError("unexpected ORM lookup in message event handler")

    db = AsyncMock()
    db.execute.side_effect = execute
    db.get.side_effect = get
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    )
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    chat = SimpleNamespace(participants=[sender], chat_type="dm", name=None)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=chat)
    repo.get_message_by_id = AsyncMock(return_value=None)

    with (
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch(
            "app.services.chat.notification_service.ChatNotificationService"
        ) as notification_class,
        patch(
            "app.api.ws.connection_manager.manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ),
    ):
        notification_class.return_value.notify_new_message = AsyncMock()
        if kind == "sent":
            await event_handlers.handle_message_sent(
                MessageSent(message_id=message_id, chat_id=chat_id)
            )
        elif kind == "edited":
            await event_handlers.handle_message_edited(
                MessageEdited(message_id=message_id, chat_id=chat_id)
            )
        else:
            await event_handlers.handle_message_deleted(
                MessageDeleted(message_id=message_id, chat_id=chat_id)
            )

    expected = ["membership"]
    if dialect == "postgresql":
        expected.append("rls_identity")
    expected.append("message_read")
    assert operations[: len(expected)] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sent", "edited", "deleted"])
async def test_message_handlers_skip_when_chat_has_no_current_member(monkeypatch, kind):
    message_id = uuid4()
    chat_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        if kind == "sent":
            await event_handlers.handle_message_sent(
                MessageSent(message_id=message_id, chat_id=chat_id)
            )
        elif kind == "edited":
            await event_handlers.handle_message_edited(
                MessageEdited(message_id=message_id, chat_id=chat_id)
            )
        else:
            await event_handlers.handle_message_deleted(
                MessageDeleted(message_id=message_id, chat_id=chat_id)
            )

    db.get.assert_not_awaited()
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sent", "edited", "deleted"])
async def test_message_handlers_skip_when_message_disappears_after_membership_check(
    monkeypatch, kind
):
    message_id = uuid4()
    chat_id = uuid4()
    member_id = uuid4()
    membership = SimpleNamespace(scalar_one_or_none=lambda: member_id)
    db = AsyncMock()
    db.execute.side_effect = [membership, None]
    db.get.return_value = None
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        if kind == "sent":
            await event_handlers.handle_message_sent(
                MessageSent(message_id=message_id, chat_id=chat_id)
            )
        elif kind == "edited":
            await event_handlers.handle_message_edited(
                MessageEdited(message_id=message_id, chat_id=chat_id)
            )
        else:
            await event_handlers.handle_message_deleted(
                MessageDeleted(message_id=message_id, chat_id=chat_id)
            )

    db.get.assert_awaited_once_with(event_handlers.models.Message, message_id)
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_edit_event_never_broadcasts_tombstoned_content(monkeypatch):
    message_id = uuid4()
    chat_id = uuid4()
    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        content="",
        edited_at=datetime.now(UTC),
        deleted_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.get.return_value = message
    _configure_message_rls_mock(db, uuid4())
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        await event_handlers.handle_message_edited(
            MessageEdited(message_id=message_id, chat_id=chat_id)
        )

    broadcast.assert_not_awaited()


def test_event_handler_configuration_subscribes_message_mutations():
    with patch.object(event_handlers.event_bus, "subscribe") as subscribe:
        event_handlers.configure_event_handlers()

    subscribe.assert_any_call(
        "chat.message_edited", event_handlers.handle_message_edited
    )
    subscribe.assert_any_call(
        "chat.message_deleted", event_handlers.handle_message_deleted
    )


@pytest.mark.asyncio
async def test_chat_delete_notifications_and_attachment_handlers():
    deleted = event_handlers.ChatDeleted(chat_id=uuid4(), participant_id=uuid4())
    with patch(
        "app.services.ws_hub_client.invalidate_ws_hub_cache",
        new_callable=AsyncMock,
    ) as invalidate:
        await event_handlers.handle_chat_deleted(deleted)
    invalidate.assert_awaited_once_with(
        str(deleted.participant_id), str(deleted.chat_id)
    )

    await event_handlers.handle_notifications_requested(
        NotificationsRequested(notification_ids=[], channel="push")
    )
    db = MagicMock()
    db.commit = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db)
    session_context.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(event_handlers, "async_session", return_value=session_context),
        patch(
            "app.services.notifications.delivery.redeliver_notifications",
            new=AsyncMock(return_value=SimpleNamespace(retryable_failures=0)),
        ),
    ):
        await event_handlers.handle_notifications_requested(
            NotificationsRequested(notification_ids=[uuid4()], channel="push")
        )

    with patch(
        "app.services.chat.attachment_service.ChatAttachmentService"
    ) as attachment_class:
        attachment_class.return_value.cleanup_files = AsyncMock()
        event = AttachmentCleanupRequested(
            chat_id=uuid4(), attachment_urls=["/static/a.png"]
        )
        await event_handlers.handle_attachment_cleanup_requested(event)
    attachment_class.return_value.cleanup_files.assert_awaited_once_with(
        ["/static/a.png"], durable=True
    )


@pytest.mark.asyncio
async def test_notification_redelivery_commits_partial_results_before_retry():
    from app.services.notifications.delivery import (
        NotificationRedeliveryError,
        NotificationRedeliveryOutcome,
    )

    db = MagicMock()
    db.commit = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db)
    session_context.__aexit__ = AsyncMock(return_value=False)
    outcome = NotificationRedeliveryOutcome(sent=1, retryable_failures=1)
    event = NotificationsRequested(notification_ids=[uuid4()], channel="push")

    with (
        patch.object(event_handlers, "async_session", return_value=session_context),
        patch(
            "app.services.notifications.delivery.redeliver_notifications",
            new=AsyncMock(return_value=outcome),
        ) as redeliver,
        pytest.raises(NotificationRedeliveryError),
    ):
        await event_handlers.handle_notifications_requested(event)

    redeliver.assert_awaited_once_with(
        db,
        notification_ids=event.notification_ids,
        channel="push",
        payload_data=None,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_notification_outbox_event_replays_original_payload_metadata():
    event = NotificationsRequested.from_dict(
        {
            "notification_ids": [str(uuid4())],
            "channel": "push",
            "payload_data": {"category": "system", "version": "9.0.0"},
        }
    )
    assert event.payload_data == {"category": "system", "version": "9.0.0"}

    db = MagicMock()
    db.commit = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db)
    session_context.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(event_handlers, "async_session", return_value=session_context),
        patch(
            "app.services.notifications.delivery.redeliver_notifications",
            new=AsyncMock(return_value=SimpleNamespace(retryable_failures=0)),
        ) as redeliver,
    ):
        await event_handlers.handle_notifications_requested(event)

    redeliver.assert_awaited_once_with(
        db,
        notification_ids=event.notification_ids,
        channel="push",
        payload_data={"category": "system", "version": "9.0.0"},
    )
    db.commit.assert_awaited_once()


def test_configure_event_handlers_registers_global_subscriptions():
    with (
        patch.object(event_handlers.event_bus, "subscribe_all") as subscribe_all,
        patch.object(event_handlers.event_bus, "subscribe") as subscribe,
    ):
        event_handlers.configure_event_handlers()

    subscribe_all.assert_called_once_with(event_handlers.log_all_events)
    assert subscribe.call_count == 29
    subscribe.assert_any_call(
        "chat.participant_removed",
        event_handlers.handle_chat_participant_removed,
    )
    subscribe.assert_any_call(
        "SCHEDULE_UPDATED", event_handlers.handle_schedule_changed
    )
    subscribe.assert_any_call(
        "SCHEDULE_DELETED", event_handlers.handle_schedule_changed
    )
    subscribe.assert_any_call(
        "notification.delivery_requested",
        event_handlers.handle_notifications_requested,
    )


@pytest.mark.asyncio
async def test_audit_only_producers_have_explicit_durable_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.events import EventBus
    from app.models.domain_events import StoredEvent
    from app.workers import outbox as outbox_module

    audit_only = {
        "SCHEDULE_CREATED",
        "GRADE_ASSIGNED",
        "GRADE_MODIFIED",
        "NOTIFICATION_DEAD_LETTER_RETRY",
        "NOTIFICATION_DEAD_LETTER_PURGE",
    }
    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    event_handlers.configure_event_handlers()
    worker = outbox_module.OutboxWorker()

    for event_type in sorted(audit_only):
        await worker._dispatch_event(
            StoredEvent(
                id=uuid4(),
                event_type=event_type,
                aggregate_type="audit",
                aggregate_id="test",
                payload={},
                metadata_={},
            )
        )


@pytest.mark.asyncio
async def test_outbox_retries_participant_eviction_publish_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.events import ChatParticipantRemoved, EventBus
    from app.models.domain_events import StoredEvent
    from app.workers import outbox as outbox_module

    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    event_handlers.configure_event_handlers()
    worker = outbox_module.OutboxWorker()
    chat_id = uuid4()
    user_id = uuid4()
    stored_event = StoredEvent(
        id=uuid4(),
        event_type=ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(chat_id),
        payload={"chat_id": str(chat_id), "user_id": str(user_id)},
        metadata_={},
    )
    mock_publish = AsyncMock(side_effect=ConnectionError("NATS unavailable"))
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", mock_publish
    )

    with pytest.raises(RuntimeError, match="Durable event handler failed"):
        await worker._dispatch_event(stored_event)

    mock_publish.assert_awaited_once_with(
        str(user_id),
        str(chat_id),
        evict_room=True,
        event_id=str(stored_event.id),
        raise_on_failure=True,
    )
