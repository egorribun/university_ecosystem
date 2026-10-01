"""Branch-only closure tests for chat command services."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

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
    chat_id = uuid.uuid4()
    uow.chats.get_by_id = AsyncMock(return_value=SimpleNamespace(id=chat_id))
    uow.chats.check_participant = AsyncMock(return_value=True)
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
            chat_id, user, "ignored", [], "en", idempotency_key="same-request"
        )

    assert result is response
    uow.chats.get_message_by_id.assert_awaited_once_with(
        message_id, user_id=user.id, chat_id=chat_id
    )


async def test_send_message_cached_result_rechecks_membership_before_message_read():
    uow = _uow()
    user = _user()
    chat_id = uuid.uuid4()
    uow.chats.get_by_id = AsyncMock(return_value=SimpleNamespace(id=chat_id))
    uow.chats.check_participant = AsyncMock(return_value=False)
    cached_message = SimpleNamespace(
        model_dump=MagicMock(return_value={}), replied_to=None, sender_id=user.id
    )
    uow.chats.get_message_by_id = AsyncMock(return_value=cached_message)
    cache = AsyncMock()
    cache.get.return_value = json.dumps({"message_id": str(uuid.uuid4())})

    with (
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(command_service, "MessageResponse", return_value=MagicMock()),
        patch.object(command_service.ReplyPreview, "from_message", return_value=None),
        patch.object(command_service.ws_manager, "is_online", return_value=False),
    ):
        with pytest.raises(HTTPException) as denied:
            await ChatMessageDispatcher(uow, MagicMock(), MagicMock()).send_message(
                chat_id,
                user,
                "ignored",
                [],
                "en",
                idempotency_key="previously-authorized-request",
            )

    assert denied.value.status_code == 403
    uow.chats.get_by_id.assert_awaited_once_with(chat_id)
    uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
    uow.chats.get_message_by_id.assert_not_awaited()


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_non_admin_maintenance_denies_before_loading_messages(operation: str):
    user = _user()
    user.role = "student"
    chat = _group_chat(user.id)
    chat.messages = [MagicMock(id=uuid.uuid4())]
    uow = _uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    service = ChatMaintenanceService(uow, MagicMock())

    with pytest.raises(HTTPException) as denied:
        await getattr(service, operation)(chat.id, user, "en")

    assert denied.value.status_code == 403
    uow.chats.get_by_id.assert_awaited_once_with(chat.id)


async def test_admin_maintenance_uses_participant_identity_only_after_authorization():
    admin = _user()
    admin.role = command_service.UserRole.ADMIN
    participant = _user()
    summary = _group_chat(participant.id)
    loaded = _group_chat(participant.id)
    loaded.id = summary.id
    loaded.messages = [MagicMock(id=uuid.uuid4())]
    uow = _uow()
    uow.chats.get_by_id = AsyncMock(side_effect=[summary, loaded])
    uow.chats.delete_messages = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    attachment_service = MagicMock()
    attachment_service.collect_urls = AsyncMock(return_value=[])

    await ChatMaintenanceService(uow, attachment_service).clear_history(
        summary.id, admin, "en"
    )

    assert [entry.args for entry in uow.chats.get_by_id.await_args_list] == [
        (summary.id,),
        (summary.id,),
    ]
    assert uow.chats.get_by_id.await_args_list[1].kwargs == {
        "load_messages": True,
        "user_id": participant.id,
    }
    uow.chats.delete_messages.assert_awaited_once_with(
        [loaded.messages[0].id], chat_id=summary.id, user_id=participant.id
    )


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_admin_maintenance_fails_closed_for_chat_without_rls_identity(
    operation: str,
):
    admin = _user()
    admin.role = command_service.UserRole.ADMIN
    orphaned_chat = _group_chat(uuid.uuid4())
    orphaned_chat.participants = []
    orphaned_chat.messages = [MagicMock(id=uuid.uuid4())]

    uow = _uow()
    uow.chats.get_by_id = AsyncMock(return_value=orphaned_chat)
    uow.chats.delete_messages = AsyncMock()
    uow.chats.delete_chat = AsyncMock()
    attachment_service = MagicMock()
    attachment_service.collect_urls = AsyncMock(return_value=[])

    service = ChatMaintenanceService(uow, attachment_service)
    with pytest.raises(HTTPException) as denied:
        await getattr(service, operation)(orphaned_chat.id, admin, "en")

    assert denied.value.status_code == 403
    uow.chats.get_by_id.assert_awaited_once_with(orphaned_chat.id)
    attachment_service.collect_urls.assert_not_awaited()
    uow.chats.delete_messages.assert_not_awaited()
    uow.chats.delete_chat.assert_not_awaited()
    uow.commit.assert_not_awaited()


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
    uow.chats.add.assert_not_called()
