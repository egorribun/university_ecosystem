"""Message edit and soft-delete service/serializer tests.

The request commits author-scoped changes and relies on the transactional outbox for
the durable WebSocket notification. It must not emit a best-effort frame itself.

Contracts:
  1. Author edit/delete → repo called → commit; outbox delivery owns the frame.
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
from app.core.events import (
    _EVENT_REGISTRY,
    EventMetadata,
    MessageDeleted,
    MessageEdited,
)
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
    async def test_success_commits_without_direct_broadcast(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        edited_at = datetime.now(UTC)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.edit_message = AsyncMock(return_value=(edited_at, 1))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).edit_message(chat.id, message_id, user, "new text", "en")

        uow.chats.edit_message.assert_awaited_once_with(
            message_id, user.id, "new text", chat_id=chat.id
        )
        uow.commit.assert_awaited_once()
        broadcast.assert_not_awaited()

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
    async def test_success_commits_without_direct_broadcast(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        deleted_at = datetime.now(UTC)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.soft_delete_message = AsyncMock(return_value=(deleted_at, 1))

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).soft_delete_message(chat.id, message_id, user, "en")

        uow.chats.soft_delete_message.assert_awaited_once_with(
            message_id, user.id, chat_id=chat.id
        )
        uow.commit.assert_awaited_once()
        broadcast.assert_not_awaited()

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


def test_message_mutation_events_are_registered_for_durable_dispatch() -> None:
    assert _EVENT_REGISTRY["chat.message_edited"] is MessageEdited
    assert _EVENT_REGISTRY["chat.message_deleted"] is MessageDeleted

    message_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    edited = MessageEdited.from_dict(
        {
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "_schema_version": 1,
            "unknown": "ignored",
            "metadata": {
                "correlation_id": "payload-controlled",
                "user_id": str(uuid.uuid4()),
                "source": "payload",
            },
        }
    )
    deleted = MessageDeleted.from_dict(
        {
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "_schema_version": 1,
        }
    )
    assert edited.message_id == message_id and edited.chat_id == chat_id
    if (
        not isinstance(edited.metadata, EventMetadata)
        or edited.metadata.user_id is not None
        or edited.metadata.correlation_id is not None
        or edited.metadata.source != "app"
    ):
        raise AssertionError("event_from_dict_metadata_is_internal")
    assert deleted.message_id == message_id and deleted.chat_id == chat_id


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


class TestMessageResponseEmptyContentTombstone:
    """Wave 205 SW4 — a soft-deleted message (D1 tombstone) carries content="" in
    the RESPONSE. MessageResponse must accept it (GET /messages serializes deleted
    rows field-by-field), while MessageCreate keeps the create-time min_length=1.

    Regression: pre-fix, MessageResponse inherited MessageBase.content min_length=1,
    so GET /messages 500'd with pydantic string_too_short the moment a chat held a
    deleted message — surfaced by W205 SW9 live verification, missed by the
    SimpleNamespace-based serialize_message tests above.
    """

    def test_message_response_accepts_empty_content_tombstone(self) -> None:
        from app.schemas.chat import MessageResponse

        resp = MessageResponse(
            content="",
            id=uuid.uuid4(),
            chat_id=uuid.uuid4(),
            sender_id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            read_status=False,
            deleted_at=datetime.now(UTC),
        )
        assert resp.content == ""
        assert resp.deleted_at is not None

    def test_message_create_still_rejects_empty_content(self) -> None:
        from pydantic import ValidationError

        from app.schemas.chat import MessageCreate

        with pytest.raises(ValidationError):
            MessageCreate(content="")
