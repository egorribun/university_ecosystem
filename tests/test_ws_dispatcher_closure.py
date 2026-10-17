"""Security regressions for WebSocket message dispatch validation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocket

from app.api.ws.dispatcher import MessageDispatcher


@pytest.mark.parametrize("chat_id", [42, {"id": "not-a-uuid"}])
@pytest.mark.asyncio
async def test_read_rejects_non_uuid_json_chat_id_before_database_access(
    chat_id: object,
) -> None:
    websocket = AsyncMock(spec=WebSocket)
    user = SimpleNamespace(id=uuid4())
    session_factory = MagicMock()
    repository = MagicMock()
    repository.check_participant = AsyncMock(return_value=False)
    repository_type = MagicMock(return_value=repository)

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    session_factory.side_effect = fake_session

    with (
        patch("app.api.ws.dispatcher.async_session", session_factory),
        patch("app.api.ws.dispatcher.ChatRepository", repository_type),
    ):
        await MessageDispatcher(MagicMock()).dispatch(
            websocket,
            user,
            None,
            {"type": "read", "chat_id": chat_id},
        )

    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Invalid chat_id format"}
    )
    session_factory.assert_not_called()
    repository_type.assert_not_called()


@pytest.mark.asyncio
async def test_read_preserves_typed_uuid_dispatch_compatibility() -> None:
    websocket = AsyncMock(spec=WebSocket)
    user = SimpleNamespace(id=uuid4())
    chat_id = uuid4()
    session_factory = MagicMock()
    repository = MagicMock()
    repository.check_participant = AsyncMock(return_value=False)
    repository_type = MagicMock(return_value=repository)

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    session_factory.side_effect = fake_session

    with (
        patch("app.api.ws.dispatcher.async_session", session_factory),
        patch("app.api.ws.dispatcher.ChatRepository", repository_type),
    ):
        await MessageDispatcher(MagicMock()).dispatch(
            websocket,
            user,
            None,
            {"type": "read", "chat_id": chat_id},
        )

    session_factory.assert_called_once_with()
    repository.check_participant.assert_awaited_once_with(chat_id, user.id)
    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Access denied"}
    )
