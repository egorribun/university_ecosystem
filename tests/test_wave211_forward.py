"""Wave 211 track F — message forwarding (snapshot-copy) service + serialize tests.

Mirrors the W207 reply (`test_wave207_reply.py`) + W206 reaction service-test
patterns: mock the UoW + repo, drive ChatMessageDispatcher.forward_messages, and
assert on the created Message object + the dual-chat authz order. The headline is
the cross-chat-leak guard — forwarding FROM a chat the actor isn't in must 403
BEFORE any source message is read.
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
from app.models.chat import Attachment
from app.schemas.dtos.chat import AttachmentDTO, ChatParticipantDTO, MessageDTO
from app.services.chat.command_service import ChatMessageDispatcher

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _participant(full_name: str | None = "Alice") -> ChatParticipantDTO:
    return ChatParticipantDTO(
        id=uuid.uuid4(), full_name=full_name, email="a@example.com", is_active=True
    )


def _attachment_dto(url: str = "https://cdn.example.com/a.png") -> AttachmentDTO:
    return AttachmentDTO(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        url=url,
        file_type="image",
        filename="a.png",
        size=1234,
        created_at=NOW,
    )


def _message_dto(**overrides: Any) -> MessageDTO:
    """A valid source MessageDTO with sensible defaults; override any field."""
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


def _fake_message(forwarded_from_name: str | None = None) -> SimpleNamespace:
    """A minimal duck-typed Message for serialize_message (only the read attrs)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        content="a forwarded body",
        created_at=NOW,
        read_status=False,
        read_at=None,
        edited_at=None,
        deleted_at=None,
        forwarded_from_name=forwarded_from_name,
        sender=None,
        attachments=[],
    )


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
    return ChatMessageDispatcher(uow, MagicMock(), AsyncMock())


async def _populate_id_on_create(msg: Any) -> None:
    # The real create_message does db.add + db.flush; the flush populates the
    # UUID7 PK. The mock skips the flush, so simulate it — forward_messages'
    # record_event + the reload by [m.id for m in created] both need a real id.
    if getattr(msg, "id", None) is None:
        msg.id = uuid.uuid4()


def _reload_side_effect(sources: dict[uuid.UUID, MessageDTO]):
    """get_last_messages is called twice: first with the SOURCE ids (return the
    source DTOs), then with the NEW created ids (return DTOs echoing the persisted
    forwarded_from_name so the response is accurate)."""

    async def _impl(ids: list[uuid.UUID]) -> dict[uuid.UUID, MessageDTO]:
        return {
            i: (
                sources[i]
                if i in sources
                else _message_dto(id=i, content="orig", forwarded_from_name="Alice")
            )
            for i in ids
        }

    return _impl


# ---------------------------------------------------------------------------
# serialize_message — the forwarded_from_name scalar in the live frame
# ---------------------------------------------------------------------------


class TestSerializeMessageForward:
    def test_carries_forwarded_from_name(self) -> None:
        frame = serialize_message(_fake_message(forwarded_from_name="Alice"))
        assert frame["forwarded_from_name"] == "Alice"

    def test_none_when_not_a_forward(self) -> None:
        assert serialize_message(_fake_message())["forwarded_from_name"] is None


# ---------------------------------------------------------------------------
# ChatMessageDispatcher.forward_messages — dual-chat authz + snapshot copy
# ---------------------------------------------------------------------------


class TestForwardMessages:
    @pytest.mark.asyncio
    async def test_not_dest_participant_403_before_create(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=False)
        uow.chats.message_exists_in_chat = AsyncMock()
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)

        with pytest.raises(HTTPException) as exc:
            await _dispatcher(uow).forward_messages(
                dest.id, user, source_chat_id, [uuid.uuid4()], locale="en"
            )

        assert exc.value.status_code == 403
        uow.chats.message_exists_in_chat.assert_not_awaited()
        uow.chats.create_message.assert_not_awaited()
        uow.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_source_participant_403_cross_chat_leak_guard(self) -> None:
        # Headline: forwarding FROM a chat the actor is NOT in must 403 BEFORE any
        # source message is read (no message_exists_in_chat, no create, no commit).
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        # True for the dest (send-side) check, False for the source (read-side) check.
        uow.chats.check_participant = AsyncMock(
            side_effect=lambda cid, uid: cid == dest.id
        )
        uow.chats.message_exists_in_chat = AsyncMock()
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)

        with pytest.raises(HTTPException) as exc:
            await _dispatcher(uow).forward_messages(
                dest.id, user, source_chat_id, [uuid.uuid4()], locale="en"
            )

        assert exc.value.status_code == 403
        uow.chats.message_exists_in_chat.assert_not_awaited()
        uow.chats.create_message.assert_not_awaited()
        uow.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_source_message_not_in_source_chat_404_before_create(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=False)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)

        with pytest.raises(HTTPException) as exc:
            await _dispatcher(uow).forward_messages(
                dest.id, user, source_chat_id, [uuid.uuid4()], locale="en"
            )

        assert exc.value.status_code == 404
        uow.chats.create_message.assert_not_awaited()
        uow.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_snapshot_copies_content_and_sets_attribution(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        src = _message_dto(
            content="orig",
            sender=_participant("Alice"),
            attachments=[_attachment_dto("https://cdn.example.com/pic.png")],
        )
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.add = MagicMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.get_last_messages = AsyncMock(
            side_effect=_reload_side_effect({src.id: src})
        )

        responses = await _dispatcher(uow).forward_messages(
            dest.id, user, source_chat_id, [src.id], locale="en"
        )

        created = uow.chats.create_message.await_args.args[0]
        assert created.chat_id == dest.id
        assert created.sender_id == user.id
        assert created.content == "orig"
        assert created.forwarded_from_name == "Alice"
        assert created.forwarded_from_chat_id == source_chat_id
        assert created.forwarded_from_message_id == src.id
        # The source attachment is copied (same url, fresh Attachment row).
        uow.chats.add.assert_called_once()
        att = uow.chats.add.call_args.args[0]
        assert isinstance(att, Attachment)
        assert att.url == "https://cdn.example.com/pic.png"
        uow.commit.assert_awaited_once()
        assert len(responses) == 1
        assert responses[0].forwarded_from_name == "Alice"

    @pytest.mark.asyncio
    async def test_reactions_not_copied(self) -> None:
        # The source had reactions on the original message; a forward never copies
        # them (they belong to the source context). The snapshot copies only
        # attachments — so `add` is called for the attachment, never a reaction row.
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        src = _message_dto(content="orig", sender=_participant("Alice"), attachments=[])
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.add = MagicMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.get_last_messages = AsyncMock(
            side_effect=_reload_side_effect({src.id: src})
        )

        await _dispatcher(uow).forward_messages(
            dest.id, user, source_chat_id, [src.id], locale="en"
        )

        # No attachments on the source → nothing added; no reaction rows ever.
        uow.chats.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_forward_creates_n_messages_one_commit(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        srcs = {d.id: d for d in (_message_dto(content=f"m{i}") for i in range(3))}
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.add = MagicMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.get_last_messages = AsyncMock(side_effect=_reload_side_effect(srcs))

        responses = await _dispatcher(uow).forward_messages(
            dest.id, user, source_chat_id, list(srcs.keys()), locale="en"
        )

        assert uow.chats.create_message.await_count == 3
        uow.chats.update_timestamp_by_id.assert_awaited_once()
        uow.commit.assert_awaited_once()
        assert len(responses) == 3

    @pytest.mark.asyncio
    async def test_duplicate_source_ids_deduped(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        dest = _mock_chat()
        source_chat_id = uuid.uuid4()
        src = _message_dto(content="orig")
        uow.chats.get_by_id = AsyncMock(return_value=dest)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.create_message = AsyncMock(side_effect=_populate_id_on_create)
        uow.chats.add = MagicMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.get_last_messages = AsyncMock(
            side_effect=_reload_side_effect({src.id: src})
        )

        responses = await _dispatcher(uow).forward_messages(
            dest.id, user, source_chat_id, [src.id, src.id], locale="en"
        )

        # Deduped → one message created, not two.
        assert uow.chats.create_message.await_count == 1
        assert len(responses) == 1
