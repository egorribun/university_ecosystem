from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.chat.command_service as COMMAND_SERVICE
from app.repositories.chat_repository import SendReceiptState
from app.schemas.dtos.chat import AttachmentDTO, MessageDTO


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.asyncio
async def test_receipt_replay_preserves_only_live_message_attachments(
    monkeypatch: pytest.MonkeyPatch, deleted: bool
) -> None:
    message_id, chat_id, user_id, attachment_id = (uuid.uuid4() for _ in range(4))
    created_at = datetime(2026, 10, 24, 23, 59, tzinfo=UTC)
    deleted_at = datetime(2026, 10, 25, tzinfo=UTC) if deleted else None
    attachment_url = "https://storage.example/private-deleted-object"
    attachment = AttachmentDTO(
        id=attachment_id,
        message_id=message_id,
        url=attachment_url,
        file_type="text/plain",
        filename="secret.txt",
        size=8,
        created_at=created_at,
    )
    message = MessageDTO(
        id=message_id,
        chat_id=chat_id,
        sender_id=user_id,
        content="" if deleted else "original message",
        created_at=created_at,
        deleted_at=deleted_at,
        attachments=[attachment],
    )
    dispatcher = COMMAND_SERVICE.ChatMessageDispatcher.__new__(
        COMMAND_SERVICE.ChatMessageDispatcher
    )
    dispatcher.repository = SimpleNamespace(
        get_message_by_id=AsyncMock(return_value=message)
    )
    monkeypatch.setattr(COMMAND_SERVICE.ws_manager, "is_online", lambda _: False)

    response = await dispatcher._send_receipt_response(
        chat_id,
        user_id,
        SendReceiptState(
            message_id=message_id,
            expires_at=created_at + timedelta(hours=25),
            observed_at=created_at,
        ),
    )

    assert response.id == message_id
    assert response.deleted_at == deleted_at
    assert response.content == ("" if deleted else "original message")
    assert len(response.attachments) == (0 if deleted else 1)
    if not deleted:
        assert response.attachments[0].url == attachment_url
