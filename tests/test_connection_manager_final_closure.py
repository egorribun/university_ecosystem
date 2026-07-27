from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket


@pytest.mark.asyncio
async def test_connection_manager_cleans_last_connection_and_logs_paths():
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    websocket = AsyncMock(spec=WebSocket)
    manager.active_connections[user_id] = {websocket}
    manager.connection_users[websocket] = user_id
    manager._last_presence_sent_at[user_id] = object()

    assert await manager.disconnect(websocket) == user_id
    assert user_id not in manager.active_connections
    assert user_id not in manager._last_presence_sent_at


@pytest.mark.asyncio
async def test_connection_manager_accepts_without_subprotocol_and_reports_online():
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    websocket = AsyncMock(spec=WebSocket)
    settings = SimpleNamespace(
        ws_max_connections_per_user=2,
        ws_message_rate=1.0,
        ws_message_burst=1.0,
    )

    with patch.object(module, "settings", settings):
        assert await manager.connect(websocket, user_id) is True

    websocket.accept.assert_awaited_once_with()
    assert manager.is_online(user_id) is True
    assert manager.is_online(uuid.uuid4()) is False
    assert manager.get_online_users() == [user_id]


@pytest.mark.asyncio
async def test_connection_manager_sends_live_messages_and_cleans_mapped_dead_peer():
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    live = AsyncMock(spec=WebSocket)
    dead = AsyncMock(spec=WebSocket)
    dead.send_json.side_effect = RuntimeError("closed")
    manager.active_connections[user_id] = {live, dead}
    manager.connection_users[dead] = user_id

    with patch.object(module, "logger") as logger:
        sent = await manager.send_to_user(user_id, {"type": "ping"})

    assert sent == 1
    live.send_json.assert_awaited_once_with({"type": "ping"})
    assert dead not in manager.active_connections[user_id]
    logger.info.assert_called_once_with("ws_batch_disconnected", user_id=str(user_id))

    assert await manager.send_to_user(user_id, {"type": "second"}) == 1
