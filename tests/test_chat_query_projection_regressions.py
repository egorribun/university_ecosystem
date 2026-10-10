"""Persisted chat-list projections through the real repository and query service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.models import UserProfile
from app.models.chat import Attachment, Chat, Message, MessageReaction
from app.repositories.chat_repository import ChatRepository
from app.schemas.dtos.chat import ChatParticipantDTO
from app.services.chat.query_service import ChatQueryService

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _utc(value):
    return value.replace(tzinfo=UTC) if value is not None else None


@pytest.mark.asyncio
async def test_chat_list_projects_persisted_participant_avatars(
    db_session, user_factory
):
    owner = await user_factory(full_name="Owner", avatar_url="/static/owner.png")
    peer = await user_factory(full_name="Peer", avatar_url="/static/peer.png")
    no_profile = await user_factory()
    outsider = await user_factory(avatar_url="/static/outsider.png")
    await db_session.execute(
        delete(UserProfile).where(UserProfile.user_id == no_profile.id)
    )
    group = Chat(
        chat_type="group",
        name="Project team",
        created_by=owner.id,
        participants=[owner, peer, no_profile],
        created_at=_NOW,
        updated_at=_NOW,
    )
    hidden = Chat(participants=[outsider], created_at=_NOW, updated_at=_NOW)
    db_session.add_all([group, hidden])
    await db_session.commit()
    group_id = group.id
    expected = {
        owner.id: ("Owner", owner.email, "/static/owner.png"),
        peer.id: ("Peer", peer.email, "/static/peer.png"),
        no_profile.id: (None, no_profile.email, None),
    }
    db_session.expunge_all()
    service = ChatQueryService(db_session, ChatRepository(db_session))
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value={}),
    ):
        response = await service.get_chats(owner, None, 20)

    assert [item.id for item in response.items] == [group_id]
    item = response.items[0]
    assert (item.chat_type, item.name, item.created_by) == (
        "group",
        "Project team",
        owner.id,
    )
    assert {
        participant.id: (
            participant.full_name,
            participant.email,
            participant.avatar_url,
        )
        for participant in item.participants
    } == expected
    assert item.last_message is None
    assert item.unread_count == 0
    assert response.has_more is False
    assert response.next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True], ids=["live", "tombstone"])
async def test_chat_list_resolves_uuid_last_message_without_coercion(
    db_session, user_factory, deleted
):
    owner = await user_factory()
    peer = await user_factory()
    outsider = await user_factory()
    chat = Chat(participants=[owner, peer], created_at=_NOW, updated_at=_NOW)
    empty = Chat(participants=[owner], created_at=_NOW, updated_at=_NOW)
    hidden = Chat(participants=[outsider], created_at=_NOW, updated_at=_NOW)
    db_session.add_all([chat, empty, hidden])
    await db_session.flush()
    original = Message(
        chat_id=hidden.id,
        sender_id=outsider.id,
        content="Private original",
        created_at=_NOW - timedelta(minutes=3),
    )
    reply_target = Message(
        chat_id=chat.id,
        sender_id=owner.id,
        content="Earlier message",
        created_at=_NOW - timedelta(minutes=2),
    )
    db_session.add_all([original, reply_target])
    await db_session.flush()
    latest = Message(
        chat_id=chat.id,
        sender_id=peer.id,
        content="" if deleted else "Forwarded snapshot",
        created_at=_NOW,
        read_status=True,
        read_at=_NOW,
        edited_at=_NOW,
        deleted_at=_NOW if deleted else None,
        reply_to_message_id=reply_target.id,
        forwarded_from_name="Original sender",
        forwarded_from_chat_id=hidden.id,
        forwarded_from_message_id=original.id,
    )
    db_session.add(latest)
    await db_session.flush()
    filename = f"chat_{chat.id}_0123456789abcdef0123456789abcdef.pdf"
    attachment = Attachment(
        message_id=latest.id,
        url=f"https://storage.example.test/static/chat_uploads/{filename}",
        filename="notes.pdf",
        file_type="document",
        size=14,
        created_at=_NOW,
    )
    db_session.add_all(
        [
            attachment,
            MessageReaction(message_id=latest.id, user_id=owner.id, emoji="👍"),
        ]
    )
    await db_session.commit()
    chat_id, empty_id, latest_id = chat.id, empty.id, latest.id
    attachment_id = attachment.id
    db_session.expunge_all()
    service = ChatQueryService(db_session, ChatRepository(db_session))
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value={}),
    ):
        response = await service.get_chats(owner, None, 20)

    by_id = {item.id: item for item in response.items}
    assert set(by_id) == {chat_id, empty_id}
    assert by_id[empty_id].last_message is None
    message = by_id[chat_id].last_message
    assert message is not None
    assert (message.id, message.chat_id, message.sender_id) == (
        latest_id,
        chat_id,
        peer.id,
    )
    assert message.content == ("" if deleted else "Forwarded snapshot")
    assert message.read_status is True
    assert _utc(message.created_at) == _NOW
    assert _utc(message.read_at) == _NOW
    assert _utc(message.edited_at) == _NOW
    assert _utc(message.deleted_at) == (_NOW if deleted else None)
    assert message.forwarded_from_name == "Original sender"
    assert message.sender is not None
    assert (message.sender.id, message.sender.email) == (peer.id, peer.email)
    assert message.reactions == []
    assert message.reply_to is None
    public = message.model_dump()
    assert "forwarded_from_chat_id" not in public
    assert "forwarded_from_message_id" not in public
    if deleted:
        assert message.attachments == []
    else:
        assert len(message.attachments) == 1
        assert message.attachments[0].id == attachment_id
        assert message.attachments[0].url == (
            f"/api/v1/chats/{chat_id}/attachments/{filename}"
        )


def test_explicit_participant_avatar_roundtrips():
    import uuid

    participant = ChatParticipantDTO(
        id=uuid.uuid4(), email="member@example.com", avatar_url="/static/avatar.png"
    )
    assert ChatParticipantDTO.model_validate(participant.model_dump()) == participant
