from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api import websocket as websocket_module
from app.api.websocket import websocket_chat
from app.core.config.storage import CHAT_MAX_WEBSOCKET_FRAME_BYTES


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.broadcast_presence = AsyncMock()
    manager.check_rate_limit.return_value = True
    manager.is_online.return_value = True
    return manager


@pytest.mark.asyncio
async def test_heartbeat_frame_reaches_dispatch_after_auth_rate_and_payload_gates() -> (
    None
):
    nonce = uuid4().hex
    frame = f'{{"type":"heartbeat_ping","nonce":"{nonce}"}}'
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace(dishka_container=None))
    websocket.client = SimpleNamespace(host="127.0.0.1")
    websocket.url = SimpleNamespace(path="/ws/chat")
    websocket.receive_text = AsyncMock(
        side_effect=[frame, WebSocketDisconnect(code=1000)]
    )
    user = SimpleNamespace(id=uuid4())
    manager = _manager()
    last_seen = datetime(2026, 10, 23, tzinfo=UTC)
    dispatcher_last_seen = AsyncMock()

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ) as authenticate,
        patch("app.api.websocket.manager", manager),
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "session")),
        ),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch(
            "app.api.websocket._update_last_seen",
            new=AsyncMock(return_value=last_seen),
        ),
        patch("app.api.ws.dispatcher.update_last_seen", dispatcher_last_seen),
        patch(
            "app.api.websocket._is_websocket_payload_within_limits",
            wraps=websocket_module._is_websocket_payload_within_limits,
        ) as payload_limits,
    ):
        await websocket_chat(websocket)

    authenticate.assert_awaited_once_with(websocket)
    manager.connect.assert_awaited_once()
    manager.check_rate_limit.assert_called_once_with(websocket)
    payload_limits.assert_called_once_with(
        frame, {"type": "heartbeat_ping", "nonce": nonce}
    )
    websocket.send_json.assert_awaited_once_with(
        {"type": "heartbeat_pong", "nonce": nonce}
    )
    dispatcher_last_seen.assert_not_awaited()
    # One connect presence publication is expected; heartbeat adds none.
    manager.broadcast_presence.assert_awaited_once()


@pytest.mark.asyncio
async def test_oversized_heartbeat_frame_is_rejected_before_rate_limit() -> None:
    nonce = uuid4().hex
    frame = f'{{"type":"heartbeat_ping","nonce":"{nonce}"}}' + (
        " " * CHAT_MAX_WEBSOCKET_FRAME_BYTES
    )
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace(dishka_container=None))
    websocket.client = SimpleNamespace(host="127.0.0.1")
    websocket.url = SimpleNamespace(path="/ws/chat")
    websocket.receive_text = AsyncMock(return_value=frame)
    user = SimpleNamespace(id=uuid4())
    manager = _manager()
    last_seen = datetime(2026, 10, 23, tzinfo=UTC)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "session")),
        ),
        patch("app.api.websocket.metrics.inc_ws_connections"),
        patch("app.api.websocket.metrics.dec_ws_connections"),
        patch(
            "app.api.websocket._update_last_seen",
            new=AsyncMock(return_value=last_seen),
        ),
    ):
        await websocket_chat(websocket)

    websocket.close.assert_awaited_once_with(code=1009, reason="Payload too large")
    manager.check_rate_limit.assert_not_called()
    websocket.send_json.assert_not_awaited()
