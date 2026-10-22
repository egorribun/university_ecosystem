"""AUD-254 regression: chat-list aggregates must preserve visible-chat behavior."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.chat import Chat, ChatReadReceipt, Message
from app.repositories.chat_repository import ChatRepository, _decode_uuid_keyset_cursor
from app.utils.pagination import encode_datetime_cursor

_BASE = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chat_list_keeps_unread_and_cursor_semantics_with_unowned_messages(
    db_session, user_factory
):
    viewer = await user_factory()
    dm_peer = await user_factory()
    group_owner = await user_factory()
    group_peer = await user_factory()
    outsider = await user_factory()
    outsider_peer = await user_factory()

    dm = Chat(
        chat_type="dm",
        participants=[viewer, dm_peer],
        created_at=_BASE,
        updated_at=_BASE,
    )
    group = Chat(
        chat_type="group",
        name="Visible group",
        created_by=group_owner.id,
        participants=[viewer, group_owner, group_peer],
        created_at=_BASE,
        updated_at=_BASE,
    )
    empty = Chat(
        chat_type="dm",
        participants=[viewer],
        created_at=_BASE,
        updated_at=_BASE,
    )
    hidden_chats = [
        Chat(
            chat_type="dm",
            participants=[outsider, outsider_peer],
            created_at=_BASE,
            updated_at=_BASE,
        )
        for _ in range(32)
    ]
    db_session.add_all([dm, group, empty, *hidden_chats])
    await db_session.flush()

    dm_read = Message(
        chat_id=dm.id,
        sender_id=dm_peer.id,
        content="Read incoming",
        created_at=_BASE,
        read_status=True,
    )
    dm_unread = Message(
        chat_id=dm.id,
        sender_id=dm_peer.id,
        content="Unread incoming",
        created_at=_BASE + timedelta(seconds=1),
        read_status=False,
    )
    dm_own = Message(
        chat_id=dm.id,
        sender_id=viewer.id,
        content="Own message",
        created_at=_BASE + timedelta(seconds=2),
        read_status=False,
    )
    dm_tombstone = Message(
        chat_id=dm.id,
        sender_id=dm_peer.id,
        content="",
        created_at=_BASE + timedelta(seconds=3),
        read_status=True,
        deleted_at=_BASE + timedelta(seconds=3),
    )
    group_before_receipt = Message(
        chat_id=group.id,
        sender_id=group_owner.id,
        content="Before read mark",
        created_at=_BASE + timedelta(seconds=1),
    )
    group_unread = Message(
        chat_id=group.id,
        sender_id=group_peer.id,
        content="After read mark",
        created_at=_BASE + timedelta(seconds=4),
    )
    group_own = Message(
        chat_id=group.id,
        sender_id=viewer.id,
        content="Own group message",
        created_at=_BASE + timedelta(seconds=5),
    )
    unrelated_messages = [
        Message(
            chat_id=hidden.id,
            sender_id=outsider.id,
            content="Unrelated private message",
            created_at=_BASE + timedelta(days=index + 1),
        )
        for index, hidden in enumerate(hidden_chats)
    ]
    receipt = ChatReadReceipt(
        chat_id=group.id,
        user_id=viewer.id,
        last_read_at=_BASE + timedelta(seconds=2),
    )
    db_session.add_all(
        [
            dm_read,
            dm_unread,
            dm_own,
            dm_tombstone,
            group_before_receipt,
            group_unread,
            group_own,
            receipt,
            *unrelated_messages,
        ]
    )
    await db_session.commit()

    repository = ChatRepository(db_session)
    first_page, first_has_more, first_cursor = await repository.get_chats_for_user(
        viewer.id, None, 1
    )
    second_page, second_has_more, second_cursor = await repository.get_chats_for_user(
        viewer.id, first_cursor, 1
    )
    final_page, final_has_more, final_cursor = await repository.get_chats_for_user(
        viewer.id, second_cursor, 1
    )

    assert first_has_more is True
    assert first_cursor is not None
    assert [
        (chat.id, unread, message_id) for chat, unread, message_id in first_page
    ] == [(group.id, 1, group_own.id)]
    assert second_has_more is True
    assert second_cursor is not None
    assert [
        (chat.id, unread, message_id) for chat, unread, message_id in second_page
    ] == [(dm.id, 1, dm_tombstone.id)]
    assert final_has_more is False
    assert final_cursor is None
    assert [
        (chat.id, unread, message_id) for chat, unread, message_id in final_page
    ] == [(empty.id, 0, None)]


def test_uuid_keyset_cursor_ignores_malformed_keys() -> None:
    key = uuid.UUID(int=701)

    assert _decode_uuid_keyset_cursor(encode_datetime_cursor(_BASE, str(key))) == (
        _BASE,
        key,
    )
    assert _decode_uuid_keyset_cursor(None) is None
    assert (
        _decode_uuid_keyset_cursor(encode_datetime_cursor(_BASE, "not-a-uuid")) is None
    )
