"""Behavior-level closure tests for domain-event handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.events import (
    AttachmentCleanupRequested,
    EventCreated,
    EventRegistration,
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


@pytest.mark.asyncio
async def test_event_and_news_embedding_handlers_cover_missing_and_success():
    missing_db = AsyncMock()
    missing_db.get.return_value = None
    with (
        patch.object(event_handlers, "async_session", lambda: _session(missing_db)),
        patch.object(event_handlers, "get_vector_service", return_value=AsyncMock()),
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
    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch.object(event_handlers, "get_vector_service", return_value=vector),
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
        patch.object(event_handlers, "get_vector_service", return_value=vector),
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
        sender_id=sender_id,
        sender=None,
        reply_to_message_id=reply_id,
    )
    sender = SimpleNamespace(id=sender_id)
    reply = SimpleNamespace(id=reply_id)
    chat = SimpleNamespace(participants=[sender], chat_type="group", name="Study")
    db = AsyncMock()
    db.get.side_effect = [message, sender]
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
    repo.get_message_by_id.assert_awaited_once_with(reply_id)
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
        ["/static/a.png"]
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
    )
    db.commit.assert_awaited_once()


def test_configure_event_handlers_registers_global_subscriptions():
    with (
        patch.object(event_handlers.event_bus, "subscribe_all") as subscribe_all,
        patch.object(event_handlers.event_bus, "subscribe") as subscribe,
    ):
        event_handlers.configure_event_handlers()

    subscribe_all.assert_called_once_with(event_handlers.log_all_events)
    assert subscribe.call_count == 15
    subscribe.assert_any_call(
        "notification.delivery_requested",
        event_handlers.handle_notifications_requested,
    )
