"""Batch message reads hydrate attachment and reply sender data from clean rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.chat import Attachment, Chat, Message
from app.repositories.chat_repository import ChatRepository

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_last_messages_hydrates_attachments_and_reply_sender(
    db_session, user_factory
):
    owner = await user_factory()
    peer = await user_factory()
    chat = Chat(participants=[owner, peer])
    db_session.add(chat)
    await db_session.flush()
    original = Message(
        chat_id=chat.id,
        sender_id=owner.id,
        content="Original",
        created_at=_NOW - timedelta(minutes=1),
    )
    db_session.add(original)
    await db_session.flush()
    reply = Message(
        chat_id=chat.id,
        sender_id=peer.id,
        content="Reply",
        reply_to_message_id=original.id,
        created_at=_NOW,
    )
    db_session.add(reply)
    await db_session.flush()
    attachment = Attachment(
        message_id=reply.id,
        url="https://storage.example.test/notes.pdf",
        file_type="document",
        filename="notes.pdf",
        size=14,
        created_at=_NOW,
    )
    db_session.add(attachment)
    await db_session.commit()
    message_id, original_id, attachment_id = reply.id, original.id, attachment.id
    db_session.expunge_all()
    rows = await ChatRepository(db_session).get_last_messages(
        [message_id], user_id=owner.id
    )
    assert set(rows) == {message_id}
    message = rows[message_id]
    assert message.sender is not None
    assert (message.sender.id, message.sender.email) == (peer.id, peer.email)
    assert len(message.attachments) == 1
    assert message.attachments[0].id == attachment_id
    assert message.attachments[0].message_id == message_id
    assert message.attachments[0].filename == "notes.pdf"
    assert message.attachments[0].size == 14
    assert message.replied_to is not None
    assert (message.replied_to.id, message.replied_to.content) == (
        original_id,
        "Original",
    )
    assert message.replied_to.sender is not None
    assert (message.replied_to.sender.id, message.replied_to.sender.email) == (
        owner.id,
        owner.email,
    )
    assert message.replied_to.replied_to is None
    db_session.expunge_all()
    assert message.model_dump()["attachments"][0]["id"] == attachment_id
