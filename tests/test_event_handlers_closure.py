"""Negative-path tests for the outbox domain-event handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.events import (
    AttachmentCleanupRequested,
    MessageSent,
    NewsCreated,
)
from app.services.event_handlers import (
    generate_news_embedding,
    handle_attachment_cleanup_requested,
    handle_message_sent,
)


def _session(db: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.asyncio
async def test_generate_news_embedding_returns_when_news_is_missing(monkeypatch):
    db = AsyncMock()
    vector_service = AsyncMock()
    db.get.return_value = None
    monkeypatch.setattr(
        "app.services.event_handlers.async_session", lambda: _session(db)
    )
    monkeypatch.setattr(
        "app.services.event_handlers.get_vector_service", lambda _db: vector_service
    )

    await generate_news_embedding(NewsCreated(news_id=uuid4(), title="Missing"))

    vector_service.get_embedding.assert_not_awaited()
    db.commit.assert_not_awaited()


def _message(sender_id):
    return SimpleNamespace(
        sender_id=sender_id,
        sender=None,
        reply_to_message_id=None,
    )


@pytest.mark.asyncio
async def test_handle_message_sent_returns_when_message_is_missing(monkeypatch):
    db = AsyncMock()
    db.get.return_value = None
    monkeypatch.setattr(
        "app.services.event_handlers.async_session", lambda: _session(db)
    )

    with (
        patch("app.repositories.chat_repository.ChatRepository"),
        patch("app.services.chat.notification_service.ChatNotificationService"),
    ):
        await handle_message_sent(MessageSent(message_id=uuid4(), chat_id=uuid4()))

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_sent_returns_when_sender_is_missing(monkeypatch):
    sender_id = uuid4()
    db = AsyncMock()
    db.get.side_effect = [_message(sender_id), None]
    monkeypatch.setattr(
        "app.services.event_handlers.async_session", lambda: _session(db)
    )

    with (
        patch("app.repositories.chat_repository.ChatRepository"),
        patch("app.services.chat.notification_service.ChatNotificationService"),
    ):
        await handle_message_sent(
            MessageSent(message_id=uuid4(), chat_id=uuid4(), sender_id=sender_id)
        )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_sent_returns_when_chat_id_is_missing(monkeypatch):
    sender_id = uuid4()
    db = AsyncMock()
    db.get.side_effect = [_message(sender_id), SimpleNamespace(id=sender_id)]
    monkeypatch.setattr(
        "app.services.event_handlers.async_session", lambda: _session(db)
    )

    with (
        patch("app.repositories.chat_repository.ChatRepository"),
        patch("app.services.chat.notification_service.ChatNotificationService"),
    ):
        await handle_message_sent(
            MessageSent(message_id=uuid4(), chat_id=None, sender_id=sender_id)
        )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_sent_returns_when_chat_is_missing(monkeypatch):
    sender_id = uuid4()
    db = AsyncMock()
    db.get.side_effect = [_message(sender_id), SimpleNamespace(id=sender_id)]
    monkeypatch.setattr(
        "app.services.event_handlers.async_session", lambda: _session(db)
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch("app.services.chat.notification_service.ChatNotificationService"),
    ):
        await handle_message_sent(
            MessageSent(message_id=uuid4(), chat_id=uuid4(), sender_id=sender_id)
        )

    repo.get_by_id.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_cleanup_handler_ignores_empty_url_list():
    with patch("app.services.chat.attachment_service.ChatAttachmentService") as service:
        await handle_attachment_cleanup_requested(
            AttachmentCleanupRequested(chat_id=uuid4(), attachment_urls=[])
        )

    service.assert_not_called()
