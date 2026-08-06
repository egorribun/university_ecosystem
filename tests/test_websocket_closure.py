"""Closure tests for websocket route authentication and cleanup paths."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import websocket_chat


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.broadcast_presence = AsyncMock()
    manager.check_rate_limit.return_value = True
    return manager


@pytest.mark.asyncio
async def test_websocket_chat_closes_when_authentication_returns_no_user():
    websocket = AsyncMock()

    with patch(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(None, None, None)),
    ):
        await websocket_chat(websocket)

    websocket.close.assert_awaited_once_with(
        code=4001, reason="Authentication required"
    )


@pytest.mark.asyncio
async def test_websocket_chat_dispatches_messages_and_handles_disconnect():
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(
        side_effect=["{}", WebSocketDisconnect(code=1000)]
    )
    user = _user()
    manager = _manager()
    last_seen = datetime.now(UTC)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(user, "jti", "subprotocol")),
        ),
        patch("app.api.websocket.manager", manager),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch(
            "app.api.ws.dispatcher.MessageDispatcher",
            return_value=SimpleNamespace(dispatch=AsyncMock()),
        ) as dispatcher,
        patch("app.api.websocket._update_last_seen", AsyncMock(return_value=last_seen)),
    ):
        await websocket_chat(websocket)

    dispatcher.return_value.dispatch.assert_awaited_once_with(
        websocket, user, "jti", {}
    )
    manager.disconnect.assert_awaited_once_with(websocket)


@pytest.mark.asyncio
async def test_websocket_chat_uses_fallback_timestamp_when_last_seen_update_fails():
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1001))
    user = _user()
    manager = _manager()
    first_seen = datetime.now(UTC)
    update_last_seen = AsyncMock(side_effect=[first_seen, OSError("db offline")])

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(user, "jti", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch("app.api.websocket._update_last_seen", update_last_seen),
    ):
        await websocket_chat(websocket)

    fallback_timestamp = manager.broadcast_presence.await_args_list[-1].args[2]
    assert isinstance(fallback_timestamp, datetime)
    assert fallback_timestamp.tzinfo is UTC
