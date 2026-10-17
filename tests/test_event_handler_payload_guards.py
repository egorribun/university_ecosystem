"""Behavior contracts for rejecting malformed or inconsistent outbox payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.events import (
    ChatParticipantRemoved,
    MessageDeleted,
    MessageEdited,
    MessageSent,
)
from app.services import event_handlers


def _session(db: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


def _configure_membership(db: AsyncMock) -> None:
    async def execute(statement, parameters=None):
        if "chat_participants" in str(statement):
            return SimpleNamespace(scalar_one_or_none=lambda: uuid4())
        return SimpleNamespace()

    db.execute.side_effect = execute
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sent", "edited", "deleted"])
@pytest.mark.parametrize("missing", ["message_id", "chat_id"])
async def test_message_events_handle_missing_identifiers_before_opening_session(
    monkeypatch: pytest.MonkeyPatch, kind: str, missing: str
) -> None:
    message_id = None if missing == "message_id" else uuid4()
    chat_id = None if missing == "chat_id" else uuid4()
    if kind == "sent":
        event = MessageSent(message_id=message_id, chat_id=chat_id)
    elif kind == "edited":
        event = MessageEdited(message_id=message_id, chat_id=chat_id)
    else:
        event = MessageDeleted(message_id=message_id, chat_id=chat_id)

    open_session = MagicMock(side_effect=AssertionError("session must not open"))
    monkeypatch.setattr(event_handlers, "async_session", open_session)

    if kind == "sent":
        await event_handlers.handle_message_sent(event)
    elif kind == "edited":
        with pytest.raises(ValueError, match="missing its identifiers"):
            await event_handlers.handle_message_edited(event)
    else:
        with pytest.raises(ValueError, match="missing its identifiers"):
            await event_handlers.handle_message_deleted(event)

    open_session.assert_not_called()


@pytest.mark.asyncio
async def test_message_sent_event_for_another_chat_is_not_notified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message_id = uuid4()
    event_chat_id = uuid4()
    row_chat_id = uuid4()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(chat_id=row_chat_id, sender_id=uuid4())
    _configure_membership(db)
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))
    repository = MagicMock()
    repository.get_by_id = AsyncMock()

    with (
        patch(
            "app.repositories.chat_repository.ChatRepository", return_value=repository
        ),
        patch(
            "app.services.chat.notification_service.ChatNotificationService"
        ) as notify,
    ):
        await event_handlers.handle_message_sent(
            MessageSent(message_id=message_id, chat_id=event_chat_id)
        )

    db.get.assert_awaited_once_with(event_handlers.models.Message, message_id)
    repository.get_by_id.assert_not_awaited()
    notify.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "state", "error"),
    [
        ("edited", "wrong_chat", "chat does not match"),
        ("edited", "not_edited", "unedited row"),
        ("deleted", "wrong_chat", "chat does not match"),
        ("deleted", "not_deleted", "live row"),
    ],
)
async def test_message_mutation_event_must_match_committed_row_state(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    state: str,
    error: str,
) -> None:
    message_id = uuid4()
    chat_id = uuid4()
    timestamp = datetime.now(UTC)
    if state == "wrong_chat":
        message = SimpleNamespace(
            id=message_id,
            chat_id=uuid4(),
            edited_at=timestamp,
            deleted_at=timestamp if kind == "deleted" else None,
        )
    elif state == "not_edited":
        message = SimpleNamespace(
            id=message_id, chat_id=chat_id, edited_at=None, deleted_at=None
        )
    else:
        message = SimpleNamespace(id=message_id, chat_id=chat_id, deleted_at=None)
    db = AsyncMock()
    db.get.return_value = message
    _configure_membership(db)
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        if kind == "edited":
            with pytest.raises(ValueError, match=error):
                await event_handlers.handle_message_edited(
                    MessageEdited(message_id=message_id, chat_id=chat_id)
                )
        else:
            with pytest.raises(ValueError, match=error):
                await event_handlers.handle_message_deleted(
                    MessageDeleted(message_id=message_id, chat_id=chat_id)
                )

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["chat_id", "user_id"])
async def test_participant_removal_without_identity_remains_retryable(
    missing: str,
) -> None:
    event = ChatParticipantRemoved(
        chat_id=None if missing == "chat_id" else uuid4(),
        user_id=None if missing == "user_id" else uuid4(),
    )

    with patch(
        "app.services.ws_hub_client.invalidate_ws_hub_cache",
        new_callable=AsyncMock,
    ) as invalidate:
        with pytest.raises(ValueError, match="missing its identifiers"):
            await event_handlers.handle_chat_participant_removed(event)

    invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_cleanup_retains_every_object_still_referenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = "https://objects.example.test/chat/shared"
    db = AsyncMock()
    query_result = MagicMock()
    query_result.scalars.return_value.all.return_value = [shared]
    db.execute.return_value = query_result
    service = MagicMock()
    service.cleanup_files = AsyncMock()
    event = event_handlers.AttachmentCleanupRequested(
        chat_id=uuid4(), attachment_urls=[shared, shared]
    )
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session(db))

    with patch(
        "app.services.chat.attachment_service.ChatAttachmentService",
        return_value=service,
    ):
        await event_handlers.handle_attachment_cleanup_requested(event)

    db.execute.assert_awaited_once()
    service.cleanup_files.assert_not_awaited()
