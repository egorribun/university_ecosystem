"""Focused lifecycle contracts for the WebSocket connection manager."""

from __future__ import annotations

import asyncio
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket
from starlette.types import Message as ASGIMessage


@pytest.mark.asyncio
async def test_concurrent_connects_cannot_bypass_per_user_connection_limit() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    first = AsyncMock(spec=WebSocket)
    second = AsyncMock(spec=WebSocket)
    first_accept_started = asyncio.Event()
    release_first_accept = asyncio.Event()
    second_connect_started = asyncio.Event()

    async def hold_first_accept(**_kwargs: object) -> None:
        first_accept_started.set()
        await release_first_accept.wait()

    async def connect_second() -> bool:
        second_connect_started.set()
        return await manager.connect(second, user_id)

    first.accept.side_effect = hold_first_accept
    settings = SimpleNamespace(
        ws_max_connections_per_user=1,
        ws_message_rate=2.0,
        ws_message_burst=3.0,
    )

    with patch.object(module, "settings", settings):
        first_task = asyncio.create_task(manager.connect(first, user_id))
        await first_accept_started.wait()
        second_task = asyncio.create_task(connect_second())
        await second_connect_started.wait()

        try:
            # The first socket is suspended inside accept while holding the
            # manager lock; the competing socket must not be accepted yet.
            assert manager._lock.locked()
            second.accept.assert_not_awaited()
        finally:
            release_first_accept.set()
            first_result, second_result = await asyncio.gather(
                first_task, second_task, return_exceptions=True
            )

    assert first_result is True
    assert second_result is False
    first.accept.assert_awaited_once_with()
    second.accept.assert_not_awaited()
    second.close.assert_awaited_once_with(code=1008, reason="Connection limit exceeded")
    assert manager.active_connections == {user_id: {first}}
    assert manager.connection_users == {first: user_id}
    assert set(manager.rate_limiters) == {first}


@pytest.mark.parametrize("with_uuid_message", [False, True], ids=["plain", "uuid-chat"])
@pytest.mark.asyncio
async def test_send_to_user_uses_real_websocket_json_boundary(
    with_uuid_message: bool,
) -> None:
    from app.api.ws.connection_manager import ConnectionManager
    from app.api.ws.serializers import serialize_message

    recipient_id = uuid.uuid4()
    message_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    sender_id = uuid.uuid4()
    reply_id = uuid.uuid4()
    if with_uuid_message:
        message = SimpleNamespace(
            id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            content="Live message",
            created_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
            read_status=False,
            read_at=None,
            edited_at=None,
            deleted_at=None,
            forwarded_from_name=None,
            sender=None,
            attachments=[],
        )
        replied = SimpleNamespace(
            id=reply_id,
            sender_id=recipient_id,
            sender=None,
            content="Quoted message",
            deleted_at=None,
        )
        payload = {
            "type": "new_message",
            "chat_id": str(chat_id),
            "message": serialize_message(message, replied=replied),
        }
    else:
        payload = {"type": "ping", "active": True}
    original_payload = deepcopy(payload)
    sent_frames: list[ASGIMessage] = []

    async def receive() -> ASGIMessage:
        return {"type": "websocket.connect"}

    async def send(frame: ASGIMessage) -> None:
        sent_frames.append(frame)

    websocket = WebSocket(
        {"type": "websocket", "path": "/ws", "headers": []},
        receive,
        send,
    )
    manager = ConnectionManager()
    assert await manager.connect(websocket, recipient_id)
    try:
        assert await manager.send_to_user(recipient_id, payload) == 1
        wire_frames = [
            frame for frame in sent_frames if frame["type"] == "websocket.send"
        ]
        assert len(wire_frames) == 1
        decoded = json.loads(wire_frames[0]["text"])
        if with_uuid_message:
            assert decoded["type"] == "new_message"
            assert decoded["chat_id"] == str(chat_id)
            assert decoded["message"]["id"] == str(message_id)
            assert decoded["message"]["chat_id"] == str(chat_id)
            assert decoded["message"]["sender_id"] == str(sender_id)
            assert decoded["message"]["reply_to"]["id"] == str(reply_id)
            assert decoded["message"]["reply_to"]["sender_id"] == str(recipient_id)
            assert decoded["message"]["created_at"] == "2026-10-21T12:00:00+00:00"
        else:
            assert decoded == payload
        assert payload == original_payload
        assert manager.is_online(recipient_id)
    finally:
        await manager.disconnect(websocket)
        await websocket.close()
