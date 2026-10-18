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


@pytest.mark.parametrize(
    ("event_type", "id_field"),
    [(EventCreated, "event_id_entity"), (NewsCreated, "news_id")],
)
def test_legacy_created_event_payload_defaults_locale(event_type, id_field) -> None:
    payload = {id_field: str(uuid4()), "title": "Existing source event"}

    event = event_type.from_dict(payload)

    assert event.locale is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "id_field", "handler_name", "model_name", "notify_name"),
    [
        (
            EventCreated,
            "event_id_entity",
            "handle_event_created_notification",
            "Event",
            "notify_about_event",
        ),
        (
            NewsCreated,
            "news_id",
            "handle_news_created_notification",
            "News",
            "notify_about_news",
        ),
    ],
)
async def test_created_notification_handler_uses_durable_locale(
    monkeypatch: pytest.MonkeyPatch,
    event_type,
    id_field,
    handler_name,
    model_name,
    notify_name,
) -> None:
    entity_id = uuid4()
    event = event_type(**{id_field: entity_id, "locale": "en"})
    record = SimpleNamespace(id=entity_id)
    db = AsyncMock()
    db.get.return_value = record
    notify = AsyncMock()
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    monkeypatch.setattr(event_handlers, notify_name, notify)

    await getattr(event_handlers, handler_name)(event)

    db.get.assert_awaited_once_with(
        getattr(event_handlers.models, model_name), entity_id
    )
    notify.assert_awaited_once_with(db, record, locale="en")
    db.commit.assert_awaited_once()


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


@pytest.mark.parametrize(
    "embedding",
    [[0.0, 0.0], [float("nan"), 0.25]],
    ids=["zero-vector", "nan-vector"],
)
@pytest.mark.parametrize(
    ("enabled", "api_key"),
    [(False, "configured-key"), (True, None)],
    ids=["disabled-provider", "missing-api-key"],
)
def test_unusable_content_embeddings_are_skipped_without_active_provider(
    monkeypatch, embedding, enabled, api_key
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "semantic_search_enabled", enabled)
    monkeypatch.setattr(settings, "embedding_api_key", api_key)

    assert event_handlers._usable_content_embedding(embedding) is False


@pytest.mark.parametrize(
    "embedding",
    [[0.0, 0.0], [float("nan"), 0.25]],
    ids=["zero-vector", "nan-vector"],
)
def test_unusable_content_embeddings_fail_when_provider_is_active(
    monkeypatch, embedding
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "configured-key")

    with pytest.raises(RuntimeError, match="no usable vector"):
        event_handlers._usable_content_embedding(embedding)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["news", "event"], ids=["news", "event"])
async def test_active_provider_projection_failure_keeps_outbox_event_retryable(
    monkeypatch, kind
):
    from app.core.config import settings
    from app.core.events import EventBus
    from app.models.domain_events import StoredEvent
    from app.workers import outbox as outbox_module

    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "configured-key")

    entity_id = uuid4()
    if kind == "news":
        event_type = NewsCreated.EVENT_TYPE
        payload = {"news_id": str(entity_id)}
        projection = SimpleNamespace(
            title="News title", content="News body", embedding=None
        )
        handler = event_handlers.generate_news_embedding
    else:
        event_type = EventCreated.EVENT_TYPE
        payload = {"event_id_entity": str(entity_id)}
        projection = SimpleNamespace(
            title="Event title",
            description="Event details",
            location="Room A",
            embedding=None,
        )
        handler = event_handlers.generate_event_embedding

    projection_db = AsyncMock()
    projection_db.get.return_value = projection
    vector = MagicMock()
    vector.get_embedding = AsyncMock(return_value=[0.0, 0.0])
    vector.close = AsyncMock()
    monkeypatch.setattr(
        event_handlers, "async_session", lambda: _session(projection_db)
    )
    monkeypatch.setattr(event_handlers, "VectorService", lambda **_: vector)

    bus = EventBus()
    bus.subscribe(event_type, handler)
    monkeypatch.setattr(outbox_module, "event_bus", bus)

    stored_event = StoredEvent(
        id=uuid4(),
        event_type=event_type,
        aggregate_type=kind,
        aggregate_id=str(entity_id),
        payload=payload,
        metadata_={},
        error_count=0,
        processed_at=None,
    )
    selection_result = MagicMock()
    selection_result.scalars.return_value.all.return_value = [stored_event]
    pending_result = MagicMock()
    pending_result.scalar_one.return_value = 1
    outbox_db = AsyncMock()
    outbox_db.execute.side_effect = [
        selection_result,
        pending_result,
        selection_result,
        pending_result,
    ]
    monkeypatch.setattr(outbox_module, "async_session", lambda: _session(outbox_db))

    worker = outbox_module.OutboxWorker(max_retries=3)

    assert await worker.process_batch() == 1
    assert stored_event.error_count == 1
    assert stored_event.processed_at is None
    assert "Durable event handler failed" in stored_event.last_error
    assert projection.embedding is None
    projection_db.commit.assert_not_awaited()

    assert await worker.process_batch() == 1
    assert stored_event.error_count == 2
    assert stored_event.processed_at is None
    assert "Durable event handler failed" in stored_event.last_error
    assert vector.get_embedding.await_count == 2
    assert vector.close.await_count == 2
    assert projection.embedding is None
    projection_db.commit.assert_not_awaited()
    assert outbox_db.commit.await_count == 2


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
        propagate_nats_failure=True,
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

    async def get(model, identity, **_kwargs):
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
    assert subscribe.call_count == 32
    subscribe.assert_any_call(
        "event.created", event_handlers.handle_event_created_notification
    )
    subscribe.assert_any_call(
        "news.created", event_handlers.handle_news_created_notification
    )
    subscribe.assert_any_call(
        "news.comment_created", event_handlers.handle_news_comment_created_notification
    )
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


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "Missing durable content identifier"),
        (object(), "Invalid durable content identifier"),
    ],
)
def test_required_event_uuid_rejects_missing_or_malformed_durable_ids(value, message):
    with pytest.raises(ValueError, match=message):
        event_handlers._required_event_uuid(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "field", "handler_name", "model_name"),
    [
        (EventCreated, "event_id_entity", "handle_event_created_notification", "Event"),
        (NewsCreated, "news_id", "handle_news_created_notification", "News"),
    ],
)
async def test_created_notification_handler_skips_deleted_source_record(
    monkeypatch, event_type, field, handler_name, model_name
):
    event_id = uuid4()
    db = AsyncMock()
    db.get.return_value = None
    notify = AsyncMock()
    notify_name = "notify_about_event" if model_name == "Event" else "notify_about_news"
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    monkeypatch.setattr(event_handlers, notify_name, notify)

    await getattr(event_handlers, handler_name)(event_type(**{field: event_id}))

    db.get.assert_awaited_once_with(
        getattr(event_handlers.models, model_name), event_id
    )
    notify.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "records",
    [
        [SimpleNamespace(news_id=uuid4(), user_id=uuid4()), None, object()],
        [SimpleNamespace(news_id=uuid4(), user_id=uuid4()), object(), None],
    ],
    ids=["missing-news", "missing-author"],
)
async def test_comment_notification_fails_closed_when_news_or_author_disappears(
    monkeypatch, records
):
    from app.core.events import NewsCommentCreated

    db = AsyncMock()
    db.get.side_effect = records
    notify = AsyncMock()
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    monkeypatch.setattr(event_handlers, "notify_about_comment", notify)

    await event_handlers.handle_news_comment_created_notification(
        NewsCommentCreated(comment_id=uuid4(), locale="en")
    )

    assert db.get.await_count == 3
    notify.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_comment_notification_commits_only_after_all_durable_sources_exist(
    monkeypatch,
):
    from app.core.events import NewsCommentCreated

    comment_id, news_id, author_id = uuid4(), uuid4(), uuid4()
    comment = SimpleNamespace(news_id=news_id, user_id=author_id)
    news = SimpleNamespace(id=news_id)
    author = SimpleNamespace(id=author_id)
    db = AsyncMock()
    db.get.side_effect = [comment, news, author]
    notify = AsyncMock()
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    monkeypatch.setattr(event_handlers, "notify_about_comment", notify)

    await event_handlers.handle_news_comment_created_notification(
        NewsCommentCreated(comment_id=comment_id, locale="en")
    )

    assert [call.args[0] for call in db.get.await_args_list] == [
        event_handlers.models.NewsComment,
        event_handlers.models.News,
        event_handlers.models.User,
    ]
    notify.assert_awaited_once_with(db, news, comment, author, locale="en")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_comment_notification_skips_deleted_comment_before_loading_sources(
    monkeypatch,
):
    from app.core.events import NewsCommentCreated

    comment_id = uuid4()
    db = AsyncMock()
    db.get.return_value = None
    notify = AsyncMock()
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    monkeypatch.setattr(event_handlers, "notify_about_comment", notify)

    await event_handlers.handle_news_comment_created_notification(
        NewsCommentCreated(comment_id=comment_id, locale="en")
    )

    db.get.assert_awaited_once_with(event_handlers.models.NewsComment, comment_id)
    notify.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_sent_nats_failure_keeps_outbox_row_retryable(monkeypatch):
    """Exercise the real dispatch chain with doubled sessions and broker I/O."""
    from app import models as app_models
    from app.api.ws.connection_manager import manager as ws_manager
    from app.core.events import EventBus
    from app.core.nats_broker import broker
    from app.models.domain_events import StoredEvent
    from app.workers import outbox as outbox_module

    message_id, chat_id, sender_id = uuid4(), uuid4(), uuid4()
    sender = SimpleNamespace(id=sender_id, profile=SimpleNamespace(full_name="Alice"))
    recipient = SimpleNamespace(id=uuid4(), profile=None)
    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        sender=None,
        content="hello",
        reply_to_message_id=None,
    )
    chat = SimpleNamespace(
        participants=[sender, recipient], chat_type="dm", name=None
    )
    handler_db = AsyncMock()
    handler_db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )

    async def execute(statement, *_args, **_kwargs):
        if "chat_participants" in str(statement):
            return SimpleNamespace(scalar_one_or_none=lambda: sender_id)
        return SimpleNamespace(all=lambda: [])

    async def get(model, *_args, **_kwargs):
        if model is app_models.Message:
            return message
        if model is app_models.User:
            return sender
        return None

    handler_db.execute = AsyncMock(side_effect=execute)
    handler_db.get = AsyncMock(side_effect=get)
    handler_db.commit = AsyncMock()
    monkeypatch.setattr(
        event_handlers, "async_session", lambda: _session(handler_db)
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=chat)

    stored_event = StoredEvent(
        id=uuid4(),
        event_type=MessageSent.EVENT_TYPE,
        aggregate_type="Message",
        aggregate_id=str(message_id),
        aggregate_id_uuid=message_id,
        payload={
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "sender_id": str(sender_id),
        },
        metadata_={},
        error_count=0,
        processed_at=None,
    )
    selection = MagicMock()
    selection.scalars.return_value.all.return_value = [stored_event]
    pending = MagicMock()
    pending.scalar_one.return_value = 1
    outbox_db = AsyncMock()
    outbox_db.execute = AsyncMock(side_effect=[selection, pending])
    outbox_db.commit = AsyncMock()
    outbox_db.add = MagicMock()
    monkeypatch.setattr(
        outbox_module, "async_session", lambda: _session(outbox_db)
    )

    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    event_handlers.configure_event_handlers()
    monkeypatch.setattr(
        ws_manager, "_get_chat_participants_cached", AsyncMock(return_value=[])
    )

    async def publish_core(_subject, _payload, *, strict=False):
        if strict:
            raise ConnectionError("NATS unavailable")

    broker_publish = AsyncMock(side_effect=publish_core)
    monkeypatch.setattr(broker, "publish_core", broker_publish)

    with (
        patch(
            "app.repositories.chat_repository.ChatRepository", return_value=repo
        ),
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={},
        ),
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ) as create,
    ):
        processed = await outbox_module.OutboxWorker(max_retries=3).process_batch()

    assert processed == 1
    assert stored_event.error_count == 1
    assert stored_event.processed_at is None
    assert stored_event.last_error is not None
    assert "Durable event handler failed" in stored_event.last_error
    outbox_db.add.assert_not_called()
    outbox_db.commit.assert_awaited_once()
    create.assert_not_awaited()
    handler_db.commit.assert_not_awaited()
    broker_publish.assert_awaited_once()
    assert broker_publish.await_args.kwargs["strict"] is True
