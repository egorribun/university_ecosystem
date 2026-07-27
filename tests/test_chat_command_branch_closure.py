"""Branch-only closure tests for chat command services."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.chat.command_service as command_service
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)


def _uow():
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@example.com"
    return user


def _group_chat(user_id: uuid.UUID):
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.chat_type = "group"
    chat.created_by = user_id
    member = MagicMock()
    member.id = user_id
    chat.participants = [member]
    chat.created_at = datetime.now(UTC)
    return chat


async def test_send_message_returns_reloaded_message_from_idempotency_cache(
    monkeypatch,
):
    uow = _uow()
    user = _user()
    cached_message = MagicMock()
    cached_message.model_dump.return_value = {}
    cached_message.replied_to = None
    cached_message.sender_id = user.id
    uow.chats.get_message_by_id = AsyncMock(return_value=cached_message)
    cache = AsyncMock()
    message_id = uuid.uuid4()
    cache.get.return_value = json.dumps({"message_id": str(message_id)})
    response = MagicMock()
    response.id = uuid.uuid4()

    with (
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(command_service, "MessageResponse", return_value=response),
        patch.object(command_service.ReplyPreview, "from_message", return_value=None),
        patch.object(command_service.ws_manager, "is_online", return_value=False),
    ):
        result = await ChatMessageDispatcher(
            uow, MagicMock(), MagicMock()
        ).send_message(
            uuid.uuid4(), user, "ignored", [], "en", idempotency_key="same-request"
        )

    assert result is response
    uow.chats.get_message_by_id.assert_awaited_once_with(message_id)


async def test_send_message_continues_when_cached_message_was_deleted():
    uow = _uow()
    user = _user()
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.chat_type = "dm"
    uow.chats.get_message_by_id = AsyncMock(return_value=None)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.create_message = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.get_last_messages = AsyncMock(return_value={})
    cache = AsyncMock()
    cache.get.return_value = json.dumps({"message_id": str(uuid.uuid4())})
    response = MagicMock()
    response.id = uuid.uuid4()

    with (
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(command_service, "MessageResponse", return_value=response),
        patch.object(command_service.ws_manager, "is_online", return_value=False),
    ):
        result = await ChatMessageDispatcher(
            uow, MagicMock(), MagicMock()
        ).send_message(chat.id, user, "new message", [], "en", idempotency_key="retry")

    assert result is response
    uow.chats.get_by_id.assert_awaited_once_with(chat.id)


async def test_send_message_phase2_failure_without_files_or_idempotency_key():
    uow = _uow()
    user = _user()
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.chat_type = "dm"
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.create_message = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    uow.commit = AsyncMock(side_effect=RuntimeError("db unavailable"))
    attachments = MagicMock()
    attachments.cleanup_files = AsyncMock()

    with pytest.raises(RuntimeError, match="db unavailable"):
        await ChatMessageDispatcher(uow, attachments, MagicMock()).send_message(
            chat.id, user, "message", [], "en"
        )

    attachments.cleanup_files.assert_not_awaited()


async def test_add_participant_skips_invalidation_when_already_present():
    user = _user()
    chat = _group_chat(user.id)
    target = _user()
    uow = _uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.get_user = AsyncMock(return_value=target)
    uow.chats.add_participant = AsyncMock(return_value=False)
    service = ChatMaintenanceService(uow, MagicMock())

    with (
        patch.object(
            command_service, "invalidate_chat_participants_cache", new=AsyncMock()
        ) as invalidate_chat,
        patch.object(
            command_service, "invalidate_presence_audience_cache", new=AsyncMock()
        ) as invalidate_presence,
    ):
        await service.add_participant(chat.id, user, target.id, "en")

    invalidate_chat.assert_not_awaited()
    invalidate_presence.assert_not_awaited()


async def test_remove_participant_skips_invalidation_when_no_row_removed():
    user = _user()
    chat = _group_chat(user.id)
    target_id = uuid.uuid4()
    uow = _uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.remove_participant = AsyncMock(return_value=0)
    service = ChatMaintenanceService(uow, MagicMock())

    with (
        patch.object(
            command_service, "invalidate_chat_participants_cache", new=AsyncMock()
        ) as invalidate_chat,
        patch.object(
            command_service, "invalidate_presence_audience_cache", new=AsyncMock()
        ) as invalidate_presence,
    ):
        await service.remove_participant(chat.id, user, target_id, "en")

    invalidate_chat.assert_not_awaited()
    invalidate_presence.assert_not_awaited()
