"""Focused route-level contracts for WebSocket ingress rejection paths."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import websocket_chat
from app.core.config.storage import CHAT_MAX_WEBSOCKET_FRAME_BYTES


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.broadcast_presence = AsyncMock()
    manager.check_rate_limit.return_value = True
    manager.is_online.return_value = False
    return manager


def _authenticated_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_raw_oversized_frame_is_rejected_before_rate_limit_and_dispatch() -> None:
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(
        return_value="x" * (CHAT_MAX_WEBSOCKET_FRAME_BYTES + 1)
    )
    user = _authenticated_user()
    manager = _manager()
    dispatcher = SimpleNamespace(dispatch=AsyncMock())
    last_seen = datetime(2026, 10, 1, tzinfo=UTC)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch("app.api.ws.dispatcher.MessageDispatcher", return_value=dispatcher),
        patch(
            "app.api.websocket._update_last_seen", new=AsyncMock(return_value=last_seen)
        ),
    ):
        await websocket_chat(websocket)

    websocket.close.assert_awaited_once_with(code=1009, reason="Payload too large")
    manager.check_rate_limit.assert_not_called()
    dispatcher.dispatch.assert_not_awaited()
    manager.disconnect.assert_awaited_once_with(websocket)


@pytest.mark.asyncio
async def test_malformed_json_sends_error_then_cleans_up_on_disconnect() -> None:
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(
        side_effect=["{malformed", WebSocketDisconnect(code=1000)]
    )
    user = _authenticated_user()
    manager = _manager()
    dispatcher = SimpleNamespace(dispatch=AsyncMock())
    last_seen = datetime(2026, 10, 1, tzinfo=UTC)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch("app.api.ws.dispatcher.MessageDispatcher", return_value=dispatcher),
        patch(
            "app.api.websocket._update_last_seen", new=AsyncMock(return_value=last_seen)
        ),
    ):
        await websocket_chat(websocket)

    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Invalid JSON"}
    )
    dispatcher.dispatch.assert_not_awaited()
    manager.disconnect.assert_awaited_once_with(websocket)
