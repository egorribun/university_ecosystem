"""Message reply and quote tests.

Covers the reply rail added in SW2 (backend) + SW3 (live frame):
  - ReplyPreview.from_message — the lean quote-preview builder (pure): truncation,
    sender-name resolution, the soft-deleted-target tombstone, None passthrough.
  - serialize_message(replied=…) — the reply_to sub-dict embedded in the live
    new_message frame (raw-UUID id + isoformat'd deleted_at, matching the
    serializer's style); None when not a reply.
  - ChatMessageDispatcher.send_message — reply_to_message_id validation (the target
    must exist AND be in THIS chat → 404 before any DB write) + construction (the
    new Message row carries reply_to_message_id).

Mirrors the W206 reaction tests' mock pattern (mock the uow + repo, no DB). The
nested-DTO self-ref, the orphaned-reply (SET NULL) case, and the recipient's live
quote are also exercised cross-user at SW9.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.ws.serializers import serialize_message
from app.schemas.chat import REPLY_PREVIEW_MAX_CHARS, ReplyPreview
from app.schemas.dtos.chat import ChatParticipantDTO, MessageDTO
from app.services.chat.command_service import ChatMessageDispatcher

NOW = datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC)


def _message_dto(**overrides: Any) -> MessageDTO:
    """A valid MessageDTO with sensible defaults; override any field."""
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "chat_id": uuid.uuid4(),
        "sender_id": uuid.uuid4(),
        "content": "hello",
        "created_at": NOW,
        "read_status": False,
    }
    data.update(overrides)
    return MessageDTO(**data)


def _participant(full_name: str | None = "Alice") -> ChatParticipantDTO:
    return ChatParticipantDTO(
        id=uuid.uuid4(), full_name=full_name, email="a@example.com", is_active=True
    )


def _fake_message() -> SimpleNamespace:
    """A minimal duck-typed Message for serialize_message (only the read attrs)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        content="a reply body",
        created_at=NOW,
        read_status=False,
        read_at=None,
        edited_at=None,
        deleted_at=None,
        forwarded_from_name=None,  # Wave 211 — serialize_message reads this scalar
        sender=None,
        attachments=[],
    )


# ---------------------------------------------------------------------------
# ReplyPreview.from_message — the lean quote-preview builder (pure)
# ---------------------------------------------------------------------------


class TestReplyPreviewFromMessage:
    def test_none_passthrough(self) -> None:
        assert ReplyPreview.from_message(None) is None

    def test_builds_all_fields(self) -> None:
        dto = _message_dto(content="original text", sender=_participant("Alice"))
        preview = ReplyPreview.from_message(dto)
        assert preview is not None
        assert preview.id == dto.id
        assert preview.sender_id == dto.sender_id
        assert preview.sender_name == "Alice"
        assert preview.content == "original text"
        assert preview.deleted_at is None

    def test_truncates_long_content(self) -> None:
        long = "x" * (REPLY_PREVIEW_MAX_CHARS + 250)
        preview = ReplyPreview.from_message(_message_dto(content=long))
        assert preview is not None
        assert len(preview.content) == REPLY_PREVIEW_MAX_CHARS

    def test_deleted_target_keeps_sender_and_flag(self) -> None:
        # A soft-deleted reply target: content cleared, deleted_at stamped. The FE
        # renders an "original deleted" placeholder, but the sender is still known.
        dto = _message_dto(content="", deleted_at=NOW, sender=_participant("Bob"))
        preview = ReplyPreview.from_message(dto)
        assert preview is not None
        assert preview.content == ""
        assert preview.deleted_at == NOW
        assert preview.sender_name == "Bob"

    def test_sender_none_yields_none_sender_name(self) -> None:
        preview = ReplyPreview.from_message(_message_dto(sender=None))
        assert preview is not None
        assert preview.sender_name is None


# ---------------------------------------------------------------------------
# serialize_message(replied=…) — the reply_to sub-dict in the live frame
# ---------------------------------------------------------------------------


class TestSerializeMessageReply:
    def test_includes_reply_to_when_replied(self) -> None:
        replied = _message_dto(content="original message", sender=_participant("Alice"))
        frame = serialize_message(_fake_message(), replied=replied)
        reply_to = frame["reply_to"]
        assert reply_to is not None
        assert reply_to["id"] == replied.id  # raw UUID (downstream default=str)
        assert reply_to["sender_id"] == replied.sender_id
        assert reply_to["sender_name"] == "Alice"
        assert reply_to["content"] == "original message"
        assert reply_to["deleted_at"] is None

    def test_deleted_target_isoformats_deleted_at(self) -> None:
        replied = _message_dto(content="", deleted_at=NOW, sender=_participant("Bob"))
        frame = serialize_message(_fake_message(), replied=replied)
        # datetime is isoformat'd inline to match the serializer's style.
        assert frame["reply_to"]["deleted_at"] == NOW.isoformat()

    def test_reply_to_none_when_not_a_reply(self) -> None:
        assert serialize_message(_fake_message())["reply_to"] is None


# ---------------------------------------------------------------------------
# ChatMessageDispatcher.send_message — reply validation + construction
# ---------------------------------------------------------------------------


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


def _mock_chat() -> MagicMock:
    chat = MagicMock()
    chat.id = uuid.uuid4()
    return chat


def _dispatcher(uow: MagicMock) -> ChatMessageDispatcher:
    # (uow, attachment_service, notification_service) — neither extra dep is
    # exercised for a text-only, non-idempotent send.
    return ChatMessageDispatcher(uow, MagicMock(), AsyncMock())


async def _populate_id_on_create(msg: Any) -> None:
    # The real create_message does db.add + db.flush; the flush is what populates
    # the UUID7 PK (the default fires at INSERT, not at Message() construction).
    # The mock skips the flush, so simulate it — send_message's record_event +
    # get_last_messages([message.id]) downstream both need a real message.id.
    if getattr(msg, "id", None) is None:
        msg.id = uuid.uuid4()


class TestSendMessageReply:
    @pytest.mark.asyncio
    async def test_invalid_reply_raises_404_before_create(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat()
        reply_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=False)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)

        with pytest.raises(HTTPException) as exc:
            await _dispatcher(uow).send_message(
                chat.id, user, "hi", [], locale="en", reply_to_message_id=reply_id
            )

        assert exc.value.status_code == 404
        uow.chats.message_exists_in_chat.assert_awaited_once_with(reply_id, chat.id)
        uow.chats.create_message.assert_not_awaited()
        uow.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_reply_sets_reply_to_message_id(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat()
        reply_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.update_timestamp_by_id = AsyncMock()
        # The response path reloads via get_last_messages; key by the requested id.
        uow.chats.get_last_messages = AsyncMock(
            side_effect=lambda ids: {ids[0]: _message_dto(id=ids[0])}
        )

        await _dispatcher(uow).send_message(
            chat.id, user, "hi", [], locale="en", reply_to_message_id=reply_id
        )

        uow.chats.message_exists_in_chat.assert_awaited_once_with(reply_id, chat.id)
        created = uow.chats.create_message.await_args.args[0]
        assert created.reply_to_message_id == reply_id
        assert created.content == "hi"
        uow.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_reply_skips_validation_and_leaves_id_none(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat()
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock()
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.get_last_messages = AsyncMock(
            side_effect=lambda ids: {ids[0]: _message_dto(id=ids[0])}
        )

        await _dispatcher(uow).send_message(chat.id, user, "hi", [], locale="en")

        uow.chats.message_exists_in_chat.assert_not_awaited()
        created = uow.chats.create_message.await_args.args[0]
        assert created.reply_to_message_id is None
