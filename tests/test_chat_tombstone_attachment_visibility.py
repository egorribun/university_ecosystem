"""Deleted Messenger messages must not keep private attachments visible."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import chat as chat_api
from app.models.chat import Message
from app.repositories.chat_repository import ChatRepository
from app.schemas.dtos.chat import AttachmentDTO, MessageDTO
from app.services.chat.query_service import ChatQueryService
from tests.conftest import call_injected

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _attachment(chat_id: uuid.UUID, message_id: uuid.UUID) -> AttachmentDTO:
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    return AttachmentDTO(
        id=uuid.uuid4(),
        message_id=message_id,
        url=f"/static/chat_uploads/{filename}",
        file_type="document",
        filename="private.pdf",
        size=14,
        created_at=_NOW,
    )


def _tombstone(chat_id: uuid.UUID, sender_id: uuid.UUID) -> MessageDTO:
    message_id = uuid.uuid4()
    return MessageDTO(
        id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        content="",
        created_at=_NOW,
        deleted_at=_NOW,
        attachments=[_attachment(chat_id, message_id)],
    )


def _chat(chat_id: uuid.UUID, user_id: uuid.UUID) -> SimpleNamespace:
    participant = SimpleNamespace(
        id=user_id,
        email="member@example.test",
        avatar_url=None,
        is_active=True,
    )
    return SimpleNamespace(
        id=chat_id,
        chat_type="dm",
        name=None,
        created_by=None,
        created_at=_NOW,
        updated_at=_NOW,
        participants=[participant],
    )


def _result(*, scalar: object = None, rows: list[object] | None = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value = rows or []
    return result


@pytest.mark.asyncio
async def test_message_history_hides_attachments_for_tombstones() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_chat(chat_id, user_id))
    repo.get_messages = AsyncMock(
        return_value=([_tombstone(chat_id, user_id)], False, None)
    )
    service = ChatQueryService(AsyncMock(), repo)

    with patch(
        "app.services.chat.query_service.build_presence_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await service.get_messages(
            chat_id, SimpleNamespace(id=user_id), None, 20, "en"
        )

    assert result.items[0].deleted_at == _NOW
    assert result.items[0].attachments == []


@pytest.mark.asyncio
async def test_chat_list_last_message_preview_hides_tombstone_attachments() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    message = _tombstone(chat_id, user_id)
    chat = _chat(chat_id, user_id)
    repo = MagicMock()
    repo.get_chats_for_user = AsyncMock(
        return_value=([(chat, 0, message.id)], False, None)
    )
    repo.get_last_messages = AsyncMock(return_value={message.id: message})
    repo.get_user_display_names = AsyncMock(return_value={})
    service = ChatQueryService(AsyncMock(), repo)

    with patch(
        "app.services.chat.query_service.build_presence_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await service.get_chats(SimpleNamespace(id=user_id), None, 20)

    assert result.items[0].last_message is not None
    assert result.items[0].last_message.deleted_at == _NOW
    assert result.items[0].last_message.attachments == []


@pytest.mark.asyncio
async def test_chat_detail_last_message_preview_hides_tombstone_attachments() -> None:
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    message = _tombstone(chat_id, user_id)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_chat(chat_id, user_id))
    repo.get_unread_count = AsyncMock(return_value=0)
    repo.get_last_message = AsyncMock(return_value=message)
    service = ChatQueryService(AsyncMock(), repo)

    with patch(
        "app.services.chat.query_service.build_presence_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await service.get_chat_details(
            chat_id, SimpleNamespace(id=user_id), "en"
        )

    assert result.last_message is not None
    assert result.last_message.deleted_at == _NOW
    assert result.last_message.attachments == []


@pytest.mark.asyncio
async def test_deleted_message_attachment_download_is_not_found_before_storage_read() -> (
    None
):
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    storage_url = f"/static/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    statements: list[str] = []

    async def execute(statement: object) -> MagicMock:
        sql = str(statement)
        statements.append(sql)
        if len(statements) == 1:
            return _result(scalar=user.id)
        # Model the database result for the deleted source attachment: it is
        # visible only while the query lacks a live-message predicate.
        if "messages.deleted_at IS NULL" in sql:
            return _result(rows=[])
        return _result(rows=[SimpleNamespace(url=storage_url, size=14)])

    db.execute.side_effect = execute
    storage = MagicMock()
    storage.read_file = AsyncMock(return_value=b"private bytes")

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=storage),
        patch.object(chat_api.ChatRepository, "set_message_rls_user", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as denied:
            await call_injected(
                chat_api.download_chat_attachment,
                chat_id,
                filename,
                current_user=user,
                locale="en",
                provides={"AsyncDatabaseSession": db},
            )

    assert denied.value.status_code == 404
    storage.read_file.assert_not_awaited()
    assert len(statements) == 2


@pytest.mark.asyncio
async def test_live_only_message_batch_excludes_tombstones_but_default_keeps_them(
    db_session, user_factory
) -> None:
    owner = await user_factory()
    peer = await user_factory()
    repository = ChatRepository(db_session)
    chat = await repository.create_chat([owner, peer])
    message = Message(
        chat_id=chat.id,
        sender_id=owner.id,
        content="",
        created_at=_NOW,
        deleted_at=_NOW,
    )
    await repository.create_message(message)

    default_batch = await repository.get_last_messages([message.id], user_id=owner.id)
    live_batch = await repository.get_last_messages(
        [message.id], user_id=owner.id, live_only=True
    )

    assert default_batch[message.id].deleted_at == _NOW
    assert live_batch == {}
