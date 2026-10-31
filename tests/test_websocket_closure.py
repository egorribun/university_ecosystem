"""Closure tests for websocket route authentication and cleanup paths."""

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import _get_websocket_audit_context, websocket_chat
from app.api.ws.connection_manager import ConnectionManager


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
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "jti")),
        ),
        patch("app.api.websocket.metrics.inc_ws_connections") as inc_connections,
        patch("app.api.websocket.metrics.dec_ws_connections") as dec_connections,
        patch(
            "app.api.websocket._update_last_seen", new=AsyncMock()
        ) as update_last_seen,
    ):
        await websocket_chat(websocket)

    websocket.receive_text.assert_not_awaited()
    manager.disconnect.assert_not_awaited()
    manager.broadcast_presence.assert_not_awaited()
    update_last_seen.assert_not_awaited()
    inc_connections.assert_not_called()
    dec_connections.assert_not_called()


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
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "jti")),
        ),
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
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "jti")),
        ),
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
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "jti")),
        ),
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
        patch(
            "app.api.websocket._resolve_user_from_ids",
            AsyncMock(return_value=(user, "jti")),
        ),
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
    manager.is_online.return_value = False
    first_seen = datetime.now(UTC)
    update_last_seen = AsyncMock(side_effect=[first_seen, OSError("db offline")])
    started = datetime.now(UTC)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(user, "jti", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch("app.api.websocket.metrics.inc_ws_connections") as inc_connections,
        patch("app.api.websocket.metrics.dec_ws_connections") as dec_connections,
        patch("app.api.websocket._update_last_seen", update_last_seen),
    ):
        await websocket_chat(websocket)

    completed = datetime.now(UTC)
    assert update_last_seen.await_count == 2
    assert manager.broadcast_presence.await_count == 2
    offline_presence = manager.broadcast_presence.await_args_list[-1]
    assert offline_presence.args[0] == user.id
    assert offline_presence.args[1] is False
    assert offline_presence.kwargs == {"source": "disconnect", "force": True}
    fallback_timestamp = offline_presence.args[2]
    assert isinstance(fallback_timestamp, datetime)
    assert fallback_timestamp.tzinfo is UTC
    assert started <= fallback_timestamp <= completed
    manager.disconnect.assert_awaited_once_with(websocket)
    inc_connections.assert_called_once_with(path="/ws/chat")
    dec_connections.assert_called_once_with(path="/ws/chat")


@pytest.fixture
def websocket_lifecycle() -> Iterator[SimpleNamespace]:
    """Keep registration real while isolating external lifecycle dependencies."""
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
    user = _user()
    manager = ConnectionManager()
    presence = AsyncMock(return_value=0)
    last_seen = datetime(2026, 10, 1, tzinfo=UTC)
    update_last_seen = AsyncMock(return_value=last_seen)

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            new=AsyncMock(return_value=(user, "session", None)),
        ),
        patch("app.api.websocket.manager", manager),
        patch.object(manager, "broadcast_presence", new=presence),
        patch("app.api.websocket._update_last_seen", new=update_last_seen),
        patch(
            "app.api.ws.dispatcher.MessageDispatcher",
            return_value=SimpleNamespace(dispatch=AsyncMock()),
        ),
        patch("app.api.websocket.metrics.inc_ws_connections") as inc_connections,
        patch("app.api.websocket.metrics.dec_ws_connections") as dec_connections,
    ):
        yield SimpleNamespace(
            websocket=websocket,
            user=user,
            manager=manager,
            presence=presence,
            last_seen=last_seen,
            update_last_seen=update_last_seen,
            inc_connections=inc_connections,
            dec_connections=dec_connections,
        )


def _assert_websocket_released(lifecycle: SimpleNamespace) -> None:
    assert not lifecycle.manager.is_online(lifecycle.user.id)
    assert not lifecycle.manager.active_connections
    assert not lifecycle.manager.connection_users
    assert not lifecycle.manager.rate_limiters
    lifecycle.inc_connections.assert_called_once_with(path="/ws/chat")
    lifecycle.dec_connections.assert_called_once_with(path="/ws/chat")


@pytest.mark.asyncio
async def test_websocket_chat_cleans_up_when_initial_last_seen_update_fails(
    websocket_lifecycle: SimpleNamespace,
) -> None:
    lifecycle = websocket_lifecycle
    failure = SQLAlchemyError("last-seen storage unavailable")
    lifecycle.update_last_seen.side_effect = [failure, lifecycle.last_seen]

    with pytest.raises(SQLAlchemyError) as raised:
        await websocket_chat(lifecycle.websocket)

    assert raised.value is failure
    _assert_websocket_released(lifecycle)
    lifecycle.websocket.receive_text.assert_not_awaited()
    lifecycle.presence.assert_awaited_once_with(
        lifecycle.user.id,
        False,
        lifecycle.last_seen,
        source="disconnect",
        force=True,
    )


@pytest.mark.asyncio
async def test_websocket_chat_cleans_up_when_online_presence_broadcast_fails(
    websocket_lifecycle: SimpleNamespace,
) -> None:
    lifecycle = websocket_lifecycle
    failure = RuntimeError("presence transport unavailable")
    lifecycle.presence.side_effect = [failure, 0]

    with pytest.raises(RuntimeError) as raised:
        await websocket_chat(lifecycle.websocket)

    assert raised.value is failure
    _assert_websocket_released(lifecycle)
    lifecycle.websocket.receive_text.assert_not_awaited()
    assert [call.args[1] for call in lifecycle.presence.await_args_list] == [
        True,
        False,
    ]
    assert lifecycle.presence.await_args.args[1] is False
    assert lifecycle.presence.await_args.kwargs == {
        "source": "disconnect",
        "force": True,
    }


@pytest.mark.asyncio
async def test_websocket_chat_uses_fallback_timestamp_when_cleanup_sqlalchemy_error(
    websocket_lifecycle: SimpleNamespace,
) -> None:
    lifecycle = websocket_lifecycle
    lifecycle.update_last_seen.side_effect = [
        lifecycle.last_seen,
        SQLAlchemyError("last-seen storage unavailable"),
    ]
    started = datetime.now(UTC)

    await websocket_chat(lifecycle.websocket)

    completed = datetime.now(UTC)
    _assert_websocket_released(lifecycle)
    assert [call.args[1] for call in lifecycle.presence.await_args_list] == [
        True,
        False,
    ]
    offline_presence = lifecycle.presence.await_args
    assert offline_presence.args[0] == lifecycle.user.id
    assert offline_presence.args[1] is False
    assert offline_presence.kwargs == {"source": "disconnect", "force": True}
    fallback_timestamp = offline_presence.args[2]
    assert isinstance(fallback_timestamp, datetime)
    assert fallback_timestamp.tzinfo is UTC
    assert started <= fallback_timestamp <= completed


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["last_seen", "presence"])
async def test_websocket_chat_preserves_cancellation_during_startup(
    websocket_lifecycle: SimpleNamespace,
    phase: str,
) -> None:
    lifecycle = websocket_lifecycle
    cancellation = asyncio.CancelledError()
    if phase == "last_seen":
        lifecycle.update_last_seen.side_effect = [cancellation, lifecycle.last_seen]
        expected_presence_states = [False]
    else:
        lifecycle.presence.side_effect = [cancellation, 0]
        expected_presence_states = [True, False]

    with pytest.raises(asyncio.CancelledError) as raised:
        await websocket_chat(lifecycle.websocket)

    assert raised.value is cancellation
    _assert_websocket_released(lifecycle)
    lifecycle.websocket.receive_text.assert_not_awaited()
    assert [call.args[1] for call in lifecycle.presence.await_args_list] == (
        expected_presence_states
    )
    assert lifecycle.presence.await_args.args[1] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(asyncio.CancelledError(), id="cancelled"),
        pytest.param(RuntimeError("unexpected cleanup failure"), id="unexpected"),
    ],
)
async def test_websocket_chat_balances_gauge_when_cleanup_is_interrupted(
    websocket_lifecycle: SimpleNamespace,
    failure: BaseException,
) -> None:
    lifecycle = websocket_lifecycle
    lifecycle.update_last_seen.side_effect = [lifecycle.last_seen, failure]

    with pytest.raises(type(failure)) as raised:
        await websocket_chat(lifecycle.websocket)

    assert raised.value is failure
    _assert_websocket_released(lifecycle)
    lifecycle.presence.assert_awaited_once_with(
        lifecycle.user.id,
        True,
        lifecycle.last_seen,
        source="connect",
        force=True,
    )


@pytest.mark.asyncio
async def test_websocket_chat_keeps_other_socket_online_after_cleanup_db_failure(
    websocket_lifecycle: SimpleNamespace,
) -> None:
    lifecycle = websocket_lifecycle
    other_socket = AsyncMock()
    assert await lifecycle.manager.connect(
        other_socket, lifecycle.user.id, session_jti="other-session"
    )
    lifecycle.update_last_seen.side_effect = [
        lifecycle.last_seen,
        SQLAlchemyError("last-seen storage unavailable"),
    ]

    try:
        await websocket_chat(lifecycle.websocket)

        assert lifecycle.manager.is_online(lifecycle.user.id)
        assert lifecycle.manager.active_connections == {
            lifecycle.user.id: {other_socket},
        }
        assert lifecycle.manager.connection_users == {
            other_socket: lifecycle.user.id,
        }
        assert set(lifecycle.manager.rate_limiters) == {other_socket}
        lifecycle.inc_connections.assert_called_once_with(path="/ws/chat")
        lifecycle.dec_connections.assert_called_once_with(path="/ws/chat")
        lifecycle.presence.assert_awaited_once_with(
            lifecycle.user.id,
            True,
            lifecycle.last_seen,
            source="connect",
            force=True,
        )
    finally:
        await lifecycle.manager.disconnect(other_socket)
