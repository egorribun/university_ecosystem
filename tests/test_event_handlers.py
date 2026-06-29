from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.events import (
    AttachmentCleanupRequested,
    ChatDeleted,
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
from app.models import Event, Message, News, User
from app.services.event_handlers import (
    configure_event_handlers,
    generate_event_embedding,
    generate_news_embedding,
    handle_attachment_cleanup_requested,
    handle_chat_deleted,
    handle_event_created,
    handle_event_registration,
    handle_message_sent,
    handle_mfa_enabled,
    handle_notification_sent,
    handle_notifications_requested,
    handle_user_created,
    handle_user_logged_in,
    log_all_events,
)


@pytest.mark.asyncio
async def test_simple_handlers():
    # Mostly for coverage as they only log
    await log_all_events(UserCreated(user_id=1, email="a@b.com", role="student"))
    await handle_user_created(UserCreated(user_id=1, email="a@b.com", role="student"))
    await handle_user_logged_in(UserLoggedIn(user_id=1, ip_address="127.0.0.1", user_agent="test"))
    await handle_mfa_enabled(MfaEnabled(user_id=1, method="totp"))
    await handle_event_created(EventCreated(event_id_entity=1, organizer_id=1, title="Test"))
    await handle_event_registration(EventRegistration(event_id_entity=1, user_id=1, registration_id=1))
    await handle_notification_sent(NotificationSent(notification_id="1", user_id=1, notification_type="test"))

@pytest.mark.asyncio
async def test_generate_event_embedding(monkeypatch):
    mock_db = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    monkeypatch.setattr("app.services.event_handlers.async_session", lambda: mock_session_ctx)
    
    mock_vector_service = AsyncMock()
    mock_vector_service.get_embedding.return_value = [0.1, 0.2]
    monkeypatch.setattr("app.services.event_handlers.get_vector_service", lambda db: mock_vector_service)
    
    mock_event = Event(id=1, title="Event", description="Desc", location="Room 1")
    mock_db.get.return_value = mock_event
    
    await generate_event_embedding(EventCreated(event_id_entity=1, organizer_id=1, title="Test"))
    
    mock_db.get.assert_called_once_with(Event, 1)
    mock_vector_service.get_embedding.assert_called_once_with("Event Desc Room 1")
    assert mock_event.embedding == [0.1, 0.2]
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_generate_event_embedding_not_found(monkeypatch):
    mock_db = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    monkeypatch.setattr("app.services.event_handlers.async_session", lambda: mock_session_ctx)
    monkeypatch.setattr("app.services.event_handlers.get_vector_service", lambda db: AsyncMock())
    
    mock_db.get.return_value = None
    
    await generate_event_embedding(EventCreated(event_id_entity=1, organizer_id=1, title="Test"))
    mock_db.commit.assert_not_called()

@pytest.mark.asyncio
async def test_generate_news_embedding(monkeypatch):
    mock_db = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    monkeypatch.setattr("app.services.event_handlers.async_session", lambda: mock_session_ctx)
    
    mock_vector_service = AsyncMock()
    mock_vector_service.get_embedding.return_value = [0.1, 0.2]
    monkeypatch.setattr("app.services.event_handlers.get_vector_service", lambda db: mock_vector_service)
    
    mock_news = News(id=1, title="News", content="Content")
    mock_db.get.return_value = mock_news
    
    await generate_news_embedding(NewsCreated(news_id=1, author_id=1))
    
    mock_db.get.assert_called_once_with(News, 1)
    mock_vector_service.get_embedding.assert_called_once_with("News Content")
    assert mock_news.embedding == [0.1, 0.2]
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_handle_message_sent(monkeypatch):
    mock_db = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    monkeypatch.setattr("app.services.event_handlers.async_session", lambda: mock_session_ctx)
    
    mock_repo = AsyncMock()
    monkeypatch.setattr("app.services.event_handlers.ChatRepository", lambda db: mock_repo)
    
    mock_service = AsyncMock()
    monkeypatch.setattr("app.services.event_handlers.ChatNotificationService", lambda db: mock_service)
    
    mock_msg = Message(id=1, sender_id=1, chat_id=1, reply_to_message_id=None)
    mock_sender = User(id=1)
    mock_db.get.side_effect = [mock_msg, mock_sender]
    
    mock_chat = MagicMock()
    mock_repo.get_by_id.return_value = mock_chat
    
    await handle_message_sent(MessageSent(message_id=1, chat_id=1, sender_id=1))
    
    mock_service.notify_new_message.assert_called_once()
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_handle_chat_deleted(monkeypatch):
    mock_invalidate = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", mock_invalidate)
    
    await handle_chat_deleted(ChatDeleted(chat_id="chat1", participant_id="p1"))
    mock_invalidate.assert_called_once_with("p1", "chat1")

@pytest.mark.asyncio
async def test_handle_notifications_requested():
    await handle_notifications_requested(NotificationsRequested(notification_ids=[]))
    await handle_notifications_requested(NotificationsRequested(notification_ids=["1"]))

@pytest.mark.asyncio
async def test_handle_attachment_cleanup_requested(monkeypatch):
    mock_service = AsyncMock()
    mock_service_cls = MagicMock(return_value=mock_service)
    monkeypatch.setattr("app.services.event_handlers.ChatAttachmentService", mock_service_cls)
    
    await handle_attachment_cleanup_requested(AttachmentCleanupRequested(chat_id="chat1", attachment_urls=["url1"]))
    mock_service.cleanup_files.assert_called_once_with(["url1"])

def test_configure_event_handlers(monkeypatch):
    mock_bus = MagicMock()
    monkeypatch.setattr("app.services.event_handlers.event_bus", mock_bus)
    
    configure_event_handlers()
    assert mock_bus.subscribe_all.call_count == 1
    assert mock_bus.subscribe.call_count > 0
