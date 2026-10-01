"""Lifecycle contracts for presence across WebSocket reconnects."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.websockets import WebSocketDisconnect


class _HeldWebSocket:
    """In-memory socket double that stays connected until released."""

    def __init__(self) -> None:
        self.accepted = asyncio.Event()
        self.release = asyncio.Event()

    async def accept(self, **_kwargs: object) -> None:
        self.accepted.set()

    async def receive_text(self) -> str:
        await self.release.wait()
        raise WebSocketDisconnect(code=1000)

    async def close(self, **_kwargs: object) -> None:
        self.release.set()


@pytest.mark.asyncio
async def test_presence_stays_online_until_last_socket_and_recovers_after_shutdown() -> (
    None
):
    from app.api import websocket as websocket_api
    from app.api.ws.connection_manager import ConnectionManager

    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)
    manager = ConnectionManager()
    presence = AsyncMock(return_value=0)
    manager.broadcast_presence = presence
    socket_one = _HeldWebSocket()
    socket_two = _HeldWebSocket()
    socket_after_reconnect = _HeldWebSocket()
    last_seen = datetime.now(UTC)

    async def wait_until_accepted(socket: _HeldWebSocket) -> None:
        await asyncio.wait_for(socket.accepted.wait(), timeout=1)

    with (
        patch.object(websocket_api, "manager", manager),
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ),
        patch.object(
            websocket_api, "_update_last_seen", new=AsyncMock(return_value=last_seen)
        ),
        patch("app.api.ws.dispatcher.MessageDispatcher", return_value=object()),
        patch.object(websocket_api.metrics, "inc_ws_connections"),
        patch.object(websocket_api.metrics, "dec_ws_connections"),
    ):
        first_task = asyncio.create_task(websocket_api.websocket_chat(socket_one))
        second_task = asyncio.create_task(websocket_api.websocket_chat(socket_two))
        await asyncio.gather(
            wait_until_accepted(socket_one), wait_until_accepted(socket_two)
        )
        manager._last_presence_sent_at[user_id] = last_seen

        socket_one.release.set()
        await first_task

        assert manager.is_online(user_id)
        assert user_id in manager._last_presence_sent_at
        assert [call.args[1] for call in presence.await_args_list] == [True, True]

        second_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second_task

        assert not manager.is_online(user_id)
        assert user_id not in manager.active_connections
        assert not manager.connection_users
        assert not manager.rate_limiters
        assert user_id not in manager._last_presence_sent_at
        assert [call.args[1] for call in presence.await_args_list] == [
            True,
            True,
            False,
        ]

        reconnect_task = asyncio.create_task(
            websocket_api.websocket_chat(socket_after_reconnect)
        )
        await wait_until_accepted(socket_after_reconnect)
        manager._last_presence_sent_at[user_id] = last_seen
        assert manager.is_online(user_id)

        socket_after_reconnect.release.set()
        await reconnect_task

    assert not manager.is_online(user_id)
    assert not manager.active_connections
    assert not manager.connection_users
    assert not manager.rate_limiters
    assert user_id not in manager._last_presence_sent_at
    assert [call.args[1] for call in presence.await_args_list] == [
        True,
        True,
        False,
        True,
        False,
    ]
