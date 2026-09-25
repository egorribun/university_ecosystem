"""Legacy forwarding shared object URLs; outbox replay must respect live owners."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import AttachmentCleanupRequested
from app.models import Attachment, Chat, Message, User
from app.services.chat.attachment_service import AttachmentCleanupError
from app.services.event_handlers import handle_attachment_cleanup_requested
from app.services.storage import StaticFSStorage

pytestmark = pytest.mark.integration


async def test_last_legacy_attachment_reference_controls_blob_lifetime(
    db_session: AsyncSession, user_factory, tmp_path: Path
) -> None:
    user: User = await user_factory()
    source_chat = Chat()
    destination_chat = Chat()
    db_session.add_all([source_chat, destination_chat])
    await db_session.flush()
    source_message = Message(
        chat_id=source_chat.id, sender_id=user.id, content="source"
    )
    destination_message = Message(
        chat_id=destination_chat.id, sender_id=user.id, content="forward"
    )
    db_session.add_all([source_message, destination_message])
    await db_session.flush()

    backend = StaticFSStorage(tmp_path, base_url="https://objects.example.test")
    url = await backend.save_file(f"chat/{uuid4().hex}.txt", b"shared")
    for message in (source_message, destination_message):
        db_session.add(
            Attachment(
                message_id=message.id,
                url=url,
                file_type="file",
                filename="shared.txt",
                size=6,
            )
        )
    await db_session.commit()

    await db_session.execute(delete(Message).where(Message.id == source_message.id))
    await db_session.commit()
    source_cleanup = AttachmentCleanupRequested(
        chat_id=source_chat.id, attachment_urls=[url]
    )
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        await asyncio.gather(
            handle_attachment_cleanup_requested(source_cleanup),
            handle_attachment_cleanup_requested(source_cleanup),
        )
        assert await backend.exists(url)
        remaining = await db_session.execute(
            select(Attachment.url).where(Attachment.url == url)
        )
        assert remaining.scalars().all() == [url]

        await db_session.execute(
            delete(Message).where(Message.id == destination_message.id)
        )
        await db_session.commit()
        last_owner_cleanup = AttachmentCleanupRequested(
            chat_id=destination_chat.id, attachment_urls=[url]
        )
        outcomes = await asyncio.gather(
            handle_attachment_cleanup_requested(last_owner_cleanup),
            handle_attachment_cleanup_requested(last_owner_cleanup),
            return_exceptions=True,
        )
        # Two distinct outbox events can race on the same legacy object. An
        # ambiguous filesystem/S3 outcome may NAK one; at-least-once replay
        # must still converge without deleting a live owner or leaking a blob.
        assert all(
            outcome is None or isinstance(outcome, AttachmentCleanupError)
            for outcome in outcomes
        )
        for outcome in outcomes:
            if isinstance(outcome, AttachmentCleanupError):
                await handle_attachment_cleanup_requested(last_owner_cleanup)
        assert not await backend.exists(url)
