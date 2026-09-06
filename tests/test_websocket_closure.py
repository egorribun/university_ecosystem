"""Closure tests for websocket route authentication and cleanup paths."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import _get_websocket_audit_context, websocket_chat


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.broadcast_presence = AsyncMock()
    manager.check_rate_limit.return_value = True
    return manager


def test_websocket_audit_context_includes_path_and_client_host():
    websocket = MagicMock()
    websocket.url.path = "/ws/chat"
    websocket.client.host = "127.0.0.1"

    assert _get_websocket_audit_context(websocket) == {
        "ws_path": "/ws/chat",
        "ws_client": "127.0.0.1",
    }


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
async def test_websocket_chat_returns_when_connection_limit_rejects_user():
    websocket = AsyncMock()
    user = _user()
    manager = _manager()
    manager.connect.return_value = False

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(user, "jti", "subprotocol")),
        ),
        patch("app.api.websocket.manager", manager),
    ):
        await websocket_chat(websocket)

    websocket.receive_text.assert_not_awaited()
    manager.disconnect.assert_not_awaited()


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
async def test_websocket_chat_allows_message_limit_with_json_overhead():
    """The content limit must not count the enclosing JSON frame."""
    websocket = AsyncMock()
    frame = json.dumps(
        {"type": "message", "payload": {"content": "x" * 32_768}},
        separators=(",", ":"),
    )
    assert len(frame) > 32_768
    websocket.receive_text = AsyncMock(
        side_effect=[frame, WebSocketDisconnect(code=1000)]
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
        websocket, user, "jti", json.loads(frame)
    )
    websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_chat_closes_when_message_content_exceeds_limit():
    websocket = AsyncMock()
    frame = json.dumps(
        {"type": "message", "payload": {"content": "x" * 32_769}},
        separators=(",", ":"),
    )
    websocket.receive_text = AsyncMock(side_effect=[frame])
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

    websocket.close.assert_awaited_once_with(code=1009, reason="Payload too large")
    dispatcher.return_value.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_chat_rejects_non_object_json_without_dispatching():
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(
        side_effect=["[]", WebSocketDisconnect(code=1000)]
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

    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Invalid JSON"}
    )
    dispatcher.return_value.dispatch.assert_not_awaited()


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
