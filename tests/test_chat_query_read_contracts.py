"""Read contracts for persisted chat rows and typed query-service boundaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete

from app.models import UserProfile
from app.models.chat import Chat, Message, MessageReaction
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import PresenceStatus
from app.schemas.dtos.chat import (
    ChatDTO,
    ChatParticipantDTO,
    MessageDTO,
    MessageReactionDTO,
)
from app.services.chat.query_service import ChatQueryService

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chat_list_retains_group_identity_and_participant_projection(
    db_session, user_factory
):
    owner = await user_factory(full_name="Owner")
    peer = await user_factory(full_name="Peer", is_active=False)
    outsider = await user_factory()
    group = Chat(
        chat_type="group",
        name="Team",
        created_by=owner.id,
        participants=[owner, peer],
        created_at=_NOW,
        updated_at=_NOW,
    )
    hidden = Chat(participants=[outsider])
    db_session.add_all([group, hidden])
    await db_session.commit()
    group_id = group.id
    expected = {
        owner.id: (owner.email, "Owner", True),
        peer.id: (peer.email, "Peer", False),
    }
    db_session.expunge_all()
    presence = {owner.id: PresenceStatus(active=True, last_seen_at=_NOW)}
    service = ChatQueryService(db_session, ChatRepository(db_session))
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value=presence),
    ):
        result = await service.get_chats(owner, None, 20)
    assert [chat.id for chat in result.items] == [group_id]
    chat = result.items[0]
    assert (chat.chat_type, chat.name, chat.created_by) == ("group", "Team", owner.id)
    assert {
        participant.id: (
            participant.email,
            participant.full_name,
            participant.is_active,
        )
        for participant in chat.participants
    } == expected
    assert chat.presence == {owner.id: presence[owner.id], peer.id: PresenceStatus()}
    assert chat.last_message is None
    assert chat.unread_count == 0
    assert result.has_more is False
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_chat_list_forwards_typed_avatar_and_last_message_metadata():
    owner = SimpleNamespace(id=uuid.uuid4())
    peer_id, chat_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    participant = ChatParticipantDTO(
        id=peer_id,
        email="peer@example.com",
        full_name="Stale DTO name",
        avatar_url="/static/peer.png",
        is_active=False,
    )
    chat = ChatDTO(
        id=chat_id,
        created_at=_NOW,
        updated_at=_NOW,
        participants=[participant],
        chat_type="group",
        name="Team",
        created_by=owner.id,
    )
    message = MessageDTO(
        id=message_id,
        chat_id=chat_id,
        sender_id=peer_id,
        sender=participant,
        content="",
        created_at=_NOW,
        read_status=True,
        read_at=_NOW,
        edited_at=_NOW,
        deleted_at=_NOW,
        forwarded_from_name="Original sender",
    )
    repository = MagicMock(spec=ChatRepository)
    repository.get_chats_for_user = AsyncMock(
        return_value=([(chat, 4, message_id)], True, "next-page")
    )
    repository.get_last_messages = AsyncMock(return_value={message_id: message})
    repository.get_user_display_names = AsyncMock(
        return_value={peer_id: "Current name"}
    )
    presence = PresenceStatus(active=True, last_seen_at=_NOW)
    service = ChatQueryService(AsyncMock(), repository)
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value={peer_id: presence}),
    ):
        result = await service.get_chats(owner, "previous-page", 1)
    repository.get_chats_for_user.assert_awaited_once_with(owner.id, "previous-page", 1)
    repository.get_last_messages.assert_awaited_once_with(
        [message_id], user_id=owner.id
    )
    assert result.has_more is True and result.next_cursor == "next-page"
    response = result.items[0]
    assert response.unread_count == 4
    assert response.created_at == response.updated_at == _NOW
    assert response.participants[0].avatar_url == "/static/peer.png"
    assert response.participants[0].full_name == "Current name"
    assert response.participants[0].is_active is False
    assert response.last_message is not None
    last = response.last_message
    assert (last.id, last.chat_id, last.sender_id) == (message_id, chat_id, peer_id)
    assert last.content == ""
    assert last.read_status is True
    assert last.read_at == last.edited_at == last.deleted_at == _NOW
    assert last.forwarded_from_name == "Original sender"
    assert last.sender.id == peer_id
    assert last.sender_presence == presence
    assert last.reply_to is None and last.reactions == []


@pytest.mark.asyncio
async def test_message_page_forwards_cursor_and_preserves_public_forward_fields():
    owner = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    chat = ChatDTO(
        id=chat_id,
        created_at=_NOW,
        updated_at=_NOW,
        participants=[ChatParticipantDTO(id=owner.id, email="owner@example.com")],
    )
    earlier = MessageDTO(
        id=uuid.uuid4(),
        chat_id=chat_id,
        sender_id=owner.id,
        content="Earlier",
        created_at=_NOW - timedelta(minutes=1),
    )
    latest = MessageDTO(
        id=uuid.uuid4(),
        chat_id=chat_id,
        sender_id=owner.id,
        content="Forward copy",
        created_at=_NOW,
        read_status=True,
        read_at=_NOW,
        edited_at=_NOW,
        forwarded_from_name="Original sender",
        replied_to=earlier,
        reactions=[MessageReactionDTO(user_id=owner.id, emoji="👍")],
    )
    repository = MagicMock(spec=ChatRepository)
    repository.get_by_id = AsyncMock(return_value=chat)
    repository.get_messages = AsyncMock(
        return_value=([latest, earlier], True, "next-page")
    )
    service = ChatQueryService(AsyncMock(), repository)
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value={}),
    ):
        result = await service.get_messages(chat_id, owner, "previous-page", 2, "en")
    repository.get_messages.assert_awaited_once_with(
        chat_id, "previous-page", 2, user_id=owner.id
    )
    assert [item.id for item in result.items] == [earlier.id, latest.id]
    assert result.has_more is True and result.next_cursor == "next-page"
    message = result.items[1]
    assert message.forwarded_from_name == "Original sender"
    assert message.read_at == message.edited_at == _NOW
    assert message.sender is None
    assert message.reply_to.id == earlier.id
    assert message.reactions[0].model_dump() == {
        "emoji": "👍",
        "count": 1,
        "reacted_by_me": True,
    }
    public = message.model_dump()
    assert "forwarded_from_chat_id" not in public
    assert "forwarded_from_message_id" not in public


@pytest.mark.asyncio
async def test_last_message_batch_hydrates_requested_live_and_deleted_rows(
    db_session, user_factory
):
    owner = await user_factory()
    peer = await user_factory()
    chat = Chat(participants=[owner, peer])
    db_session.add(chat)
    await db_session.flush()
    live = Message(chat_id=chat.id, sender_id=peer.id, content="Live", created_at=_NOW)
    deleted = Message(
        chat_id=chat.id,
        sender_id=peer.id,
        content="",
        created_at=_NOW,
        deleted_at=_NOW,
        forwarded_from_name="Original sender",
    )
    unrelated = Message(chat_id=chat.id, sender_id=owner.id, content="Unrequested")
    db_session.add_all([live, deleted, unrelated])
    await db_session.commit()
    live_id, deleted_id = live.id, deleted.id
    db_session.expunge_all()
    repository = ChatRepository(db_session)
    rows = await repository.get_last_messages([live_id, deleted_id], user_id=owner.id)
    visible = await repository.get_last_messages(
        [live_id, deleted_id], user_id=owner.id, live_only=True
    )
    assert set(rows) == {live_id, deleted_id}
    assert set(visible) == {live_id}
    assert rows[deleted_id].content == ""
    assert rows[deleted_id].deleted_at is not None
    assert rows[deleted_id].forwarded_from_name == "Original sender"
    for row in rows.values():
        assert row.sender is not None
        assert (row.sender.id, row.sender.email) == (peer.id, peer.email)
        public = row.model_dump()
        assert "forwarded_from_chat_id" not in public
        assert "forwarded_from_message_id" not in public


@pytest.mark.asyncio
async def test_reactors_are_scoped_to_message_and_emoji_and_load_profiles(
    db_session, user_factory
):
    owner = await user_factory(full_name="Owner", avatar_url="/static/owner.png")
    peer = await user_factory(full_name="Peer", avatar_url="/static/peer.png")
    chat = Chat(participants=[owner, peer])
    db_session.add(chat)
    await db_session.flush()
    first = Message(chat_id=chat.id, sender_id=owner.id, content="First")
    second = Message(chat_id=chat.id, sender_id=owner.id, content="Second")
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add_all(
        [
            MessageReaction(message_id=first.id, user_id=owner.id, emoji="👍"),
            MessageReaction(message_id=first.id, user_id=peer.id, emoji="❤️"),
            MessageReaction(message_id=second.id, user_id=peer.id, emoji="👍"),
        ]
    )
    await db_session.commit()
    chat_id, message_id = chat.id, first.id
    db_session.expunge_all()
    result = await ChatQueryService(
        db_session, ChatRepository(db_session)
    ).get_reactors(chat_id, message_id, "👍", owner, "en")
    assert [item.model_dump() for item in result] == [
        {"user_id": owner.id, "name": "Owner", "avatar_url": "/static/owner.png"}
    ]


@pytest.mark.asyncio
async def test_display_names_include_missing_profiles_and_requested_missing_users(
    db_session, user_factory
):
    owner = await user_factory(full_name="Owner")
    no_profile = await user_factory(full_name="Removed profile")
    outsider = await user_factory(full_name="Unrequested")
    await db_session.execute(
        delete(UserProfile).where(UserProfile.user_id == no_profile.id)
    )
    await db_session.commit()
    db_session.expunge_all()
    missing = uuid.uuid4()
    repository = ChatRepository(db_session)
    assert await repository.get_user_display_names([]) == {}
    result = await repository.get_user_display_names([owner.id, no_profile.id, missing])
    assert result == {owner.id: "Owner", no_profile.id: None, missing: None}
    assert outsider.id not in result
