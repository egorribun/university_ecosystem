"""Wave 205 SW4 — message edit + soft-delete (ChatMaintenanceService + serializer).

Mirrors the W203 mark_read tests (tests/test_chat_command_service.py): mock the uow +
repo, patch ws_manager.broadcast_to_chat, assert the synchronous-broadcast contract.

Contracts:
  1. Author edit/delete → repo called → commit → message_edited / message_deleted
     frame broadcast to ALL participants (exclude_user_id omitted, D3) with the
     authoritative content/edited_at | deleted_at.
  2. affected == 0 (non-author / missing / already-deleted) → 404, raised BEFORE
     commit (nothing persisted) and NO broadcast.
  3. Non-participant → 403, before the repo edit/delete is even attempted.
  4. serialize_message surfaces edited_at + deleted_at (W203 SW8 field-drop gotcha).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.ws.serializers import serialize_message
from app.services.chat.command_service import ChatMaintenanceService

BROADCAST = "app.services.chat.command_service.ws_manager.broadcast_to_chat"


def _mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = "student"
    return user


def _mock_chat(*participant_ids: uuid.UUID) -> MagicMock:
    chat = MagicMock()
    chat.id = uuid.uuid4()
    parts = []
    for pid in participant_ids:
        p = MagicMock()
        p.id = pid
        parts.append(p)
    chat.participants = parts
    return chat


def _svc(uow: MagicMock) -> ChatMaintenanceService:
    return ChatMaintenanceService(uow, MagicMock())


# ---------------------------------------------------------------------------
# edit_message
# ---------------------------------------------------------------------------


class TestEditMessage:
    @pytest.mark.asyncio
    async def test_success_broadcasts_message_edited(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        edited_at = datetime.now(UTC)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.edit_message = AsyncMock(return_value=(edited_at, 1))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).edit_message(chat.id, message_id, user, "new text", "en")

        uow.chats.edit_message.assert_awaited_once_with(message_id, user.id, "new text")
        uow.commit.assert_awaited_once()
        broadcast.assert_awaited_once()
        call = broadcast.await_args
        assert call.args[0] == chat.id
        frame = call.args[1]
        assert frame["type"] == "message_edited"
        assert frame["message_id"] == str(message_id)
        assert frame["chat_id"] == str(chat.id)
        assert frame["content"] == "new text"
        assert frame["edited_at"] == edited_at.isoformat()
        # D3 — broadcast to ALL participants (idempotent FE cache-update).
        assert call.kwargs.get("exclude_user_id") is None

    @pytest.mark.asyncio
    async def test_not_author_raises_404_before_commit(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.edit_message = AsyncMock(return_value=(None, 0))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            with pytest.raises(HTTPException) as exc:
                await _svc(uow).edit_message(chat.id, uuid.uuid4(), user, "x", "en")

        assert exc.value.status_code == 404
        uow.commit.assert_not_awaited()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_participant_raises_403_without_repo_call(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)  # user NOT a participant
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.edit_message = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _svc(uow).edit_message(chat.id, uuid.uuid4(), user, "x", "en")

        assert exc.value.status_code == 403
        uow.chats.edit_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# soft_delete_message
# ---------------------------------------------------------------------------


class TestSoftDeleteMessage:
    @pytest.mark.asyncio
    async def test_success_broadcasts_message_deleted(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        deleted_at = datetime.now(UTC)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.soft_delete_message = AsyncMock(return_value=(deleted_at, 1))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).soft_delete_message(chat.id, message_id, user, "en")

        uow.chats.soft_delete_message.assert_awaited_once_with(message_id, user.id)
        uow.commit.assert_awaited_once()
        broadcast.assert_awaited_once()
        call = broadcast.await_args
        assert call.args[0] == chat.id
        frame = call.args[1]
        assert frame["type"] == "message_deleted"
        assert frame["message_id"] == str(message_id)
        assert frame["chat_id"] == str(chat.id)
        assert frame["deleted_at"] == deleted_at.isoformat()
        assert "content" not in frame  # tombstone frame carries no content
        assert call.kwargs.get("exclude_user_id") is None

    @pytest.mark.asyncio
    async def test_not_author_raises_404_before_commit(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.soft_delete_message = AsyncMock(return_value=(None, 0))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            with pytest.raises(HTTPException) as exc:
                await _svc(uow).soft_delete_message(chat.id, uuid.uuid4(), user, "en")

        assert exc.value.status_code == 404
        uow.commit.assert_not_awaited()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_participant_raises_403_without_repo_call(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.soft_delete_message = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _svc(uow).soft_delete_message(chat.id, uuid.uuid4(), user, "en")

        assert exc.value.status_code == 403
        uow.chats.soft_delete_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# serialize_message — W203 SW8 field-drop gotcha guard
# ---------------------------------------------------------------------------


class TestSerializerFields:
    def _msg(
        self, *, edited_at: datetime | None, deleted_at: datetime | None
    ) -> MagicMock:
        m = MagicMock()
        m.id = uuid.uuid4()
        m.chat_id = uuid.uuid4()
        m.sender_id = uuid.uuid4()
        m.content = "hi"
        m.created_at = datetime.now(UTC)
        m.read_status = False
        m.read_at = None
        m.edited_at = edited_at
        m.deleted_at = deleted_at
        m.sender = None
        m.attachments = []
        return m

    def test_includes_edited_and_deleted_when_set(self) -> None:
        edited_at = datetime.now(UTC)
        deleted_at = datetime.now(UTC)
        frame = serialize_message(self._msg(edited_at=edited_at, deleted_at=deleted_at))
        assert frame["edited_at"] == edited_at.isoformat()
        assert frame["deleted_at"] == deleted_at.isoformat()

    def test_none_when_unset(self) -> None:
        frame = serialize_message(self._msg(edited_at=None, deleted_at=None))
        assert frame["edited_at"] is None
        assert frame["deleted_at"] is None
