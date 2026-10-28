"""Comprehensive tests for app/api/ws/dispatcher.py — MessageDispatcher.

Covers direct-backend message types: ping, legacy read, get_online, unknown.
Tests participant validation, admin checks, error handling, and audit logging.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from starlette.websockets import WebSocketDisconnect

from app.api.ws.dispatcher import MessageDispatcher
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.models.enums import UserRole


class _PermissionCheckerProvider(Provider):
    """Real Dishka REQUEST provider that records scope enter/exit in tests."""

    def __init__(self, checker: PermissionChecker, lifecycle: dict[str, int]) -> None:
        super().__init__()
        self._checker = checker
        self._lifecycle = lifecycle

    @provide(scope=Scope.REQUEST)
    async def permission_checker(self) -> AsyncIterator[PermissionChecker]:
        self._lifecycle["opened"] += 1
        try:
            yield self._checker
        finally:
            self._lifecycle["closed"] += 1


def _permission_container(
    checker: PermissionChecker, lifecycle: dict[str, int]
) -> AsyncContainer:
    return make_async_container(_PermissionCheckerProvider(checker, lifecycle))


# ---------------------------------------------------------------------------
# ping handler
# ---------------------------------------------------------------------------


class TestDispatchPing:
    @pytest.mark.asyncio
    async def test_ping_sends_pong(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        with patch(
            "app.api.ws.dispatcher.update_last_seen",
            new_callable=AsyncMock,
            return_value=datetime.now(UTC),
        ):
            await ws_dispatcher.dispatch(
                mock_websocket, mock_user, "test-jti", {"type": "ping"}
            )

        mock_websocket.send_json.assert_called_once_with({"type": "pong"})

    @pytest.mark.asyncio
    async def test_ping_broadcasts_presence(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        now = datetime.now(UTC)
        with patch(
            "app.api.ws.dispatcher.update_last_seen",
            new_callable=AsyncMock,
            return_value=now,
        ):
            await ws_dispatcher.dispatch(
                mock_websocket, mock_user, "test-jti", {"type": "ping"}
            )

        mock_conn_manager.broadcast_presence.assert_called_once()
        call_args = mock_conn_manager.broadcast_presence.call_args
        assert call_args[0][0] == mock_user.id  # user_id
        assert call_args[0][1] is True  # active

    @pytest.mark.asyncio
    async def test_ping_updates_last_seen(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        mock_update = AsyncMock(return_value=datetime.now(UTC))
        with patch("app.api.ws.dispatcher.update_last_seen", mock_update):
            await ws_dispatcher.dispatch(
                mock_websocket, mock_user, "test-jti", {"type": "ping"}
            )

        mock_update.assert_called_once_with("test-jti")


# ---------------------------------------------------------------------------
# heartbeat_ping handler
# ---------------------------------------------------------------------------


class TestDispatchHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_ping_echoes_valid_nonce_without_presence_mutation(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        nonce = uuid.uuid4().hex
        update_last_seen = AsyncMock()
        with patch("app.api.ws.dispatcher.update_last_seen", update_last_seen):
            await ws_dispatcher.dispatch(
                mock_websocket,
                mock_user,
                "test-jti",
                {"type": "heartbeat_ping", "nonce": nonce},
            )

        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "heartbeat_pong", "nonce": nonce}
        )
        update_last_seen.assert_not_awaited()
        mock_conn_manager.broadcast_presence.assert_not_awaited()

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"type": "heartbeat_ping"}, id="missing-nonce"),
            pytest.param({"type": "heartbeat_ping", "nonce": None}, id="null-nonce"),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": 123}, id="non-string-nonce"
            ),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": "0" * 31}, id="short-nonce"
            ),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": "0" * 33}, id="long-nonce"
            ),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": "A" * 32}, id="uppercase-nonce"
            ),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": "g" * 32}, id="non-hex-nonce"
            ),
            pytest.param(
                {"type": "heartbeat_ping", "nonce": "0" * 31 + "\n"}, id="newline-nonce"
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_invalid_nonce_returns_static_error_without_echo_or_presence(
        self, payload, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        update_last_seen = AsyncMock()
        with patch("app.api.ws.dispatcher.update_last_seen", update_last_seen):
            await ws_dispatcher.dispatch(mock_websocket, mock_user, "test-jti", payload)

        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "error", "message": "Invalid heartbeat nonce"}
        )
        update_last_seen.assert_not_awaited()
        mock_conn_manager.broadcast_presence.assert_not_awaited()


# ---------------------------------------------------------------------------
# read handler
# ---------------------------------------------------------------------------


class TestDispatchRead:
    @pytest.mark.asyncio
    async def test_read_marks_chat_and_broadcasts(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        # Legacy direct-backend path: chat-level bulk-mark and live broadcast.
        chat_id = str(uuid.uuid4())
        read_at = datetime.now(UTC)

        mock_repo = MagicMock()
        mock_repo.check_participant = AsyncMock(return_value=True)
        mock_repo.get_chat_type = AsyncMock(return_value="dm")
        mock_repo.mark_messages_read = AsyncMock(return_value=(read_at, 2))

        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield mock_session

        with (
            patch("app.api.ws.dispatcher.async_session", fake_session),
            patch("app.api.ws.dispatcher.ChatRepository", return_value=mock_repo),
        ):
            await ws_dispatcher.dispatch(
                mock_websocket,
                mock_user,
                "test-jti",
                {"type": "read", "chat_id": chat_id},
            )

        mock_repo.mark_messages_read.assert_called_once_with(
            uuid.UUID(chat_id), mock_user.id, "dm"
        )
        mock_session.commit.assert_called_once()
        mock_conn_manager.broadcast_to_chat.assert_called_once()
        call = mock_conn_manager.broadcast_to_chat.call_args
        assert call.args[0] == uuid.UUID(chat_id)
        frame = call.args[1]
        assert frame["type"] == "read"
        assert frame["chat_id"] == chat_id
        assert frame["user_id"] == str(mock_user.id)
        assert frame["read_at"] == read_at.isoformat()
        assert call.kwargs["exclude_user_id"] == mock_user.id

    @pytest.mark.asyncio
    async def test_read_non_participant_denied(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        chat_id = str(uuid.uuid4())

        mock_repo = MagicMock()
        mock_repo.check_participant = AsyncMock(return_value=False)

        @asynccontextmanager
        async def fake_session():
            yield AsyncMock()

        with (
            patch("app.api.ws.dispatcher.async_session", fake_session),
            patch("app.api.ws.dispatcher.ChatRepository", return_value=mock_repo),
        ):
            await ws_dispatcher.dispatch(
                mock_websocket,
                mock_user,
                "test-jti",
                {"type": "read", "chat_id": chat_id},
            )

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"
        mock_conn_manager.broadcast_to_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_no_unread_skips_broadcast(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        """When nothing new is marked read (affected == 0), no receipt is sent."""
        chat_id = str(uuid.uuid4())

        mock_repo = MagicMock()
        mock_repo.check_participant = AsyncMock(return_value=True)
        mock_repo.get_chat_type = AsyncMock(return_value="dm")
        mock_repo.mark_messages_read = AsyncMock(return_value=(datetime.now(UTC), 0))

        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield mock_session

        with (
            patch("app.api.ws.dispatcher.async_session", fake_session),
            patch("app.api.ws.dispatcher.ChatRepository", return_value=mock_repo),
        ):
            await ws_dispatcher.dispatch(
                mock_websocket,
                mock_user,
                "test-jti",
                {"type": "read", "chat_id": chat_id},
            )

        mock_repo.mark_messages_read.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_conn_manager.broadcast_to_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_missing_ids(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        """Missing chat_id is silently ignored (no-op, no error frame)."""
        await ws_dispatcher.dispatch(
            mock_websocket,
            mock_user,
            "test-jti",
            {"type": "read"},
        )
        mock_websocket.send_json.assert_not_called()
        mock_conn_manager.broadcast_to_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_invalid_chat_id_format(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        """A malformed chat_id is rejected with an error frame (no DB work)."""
        await ws_dispatcher.dispatch(
            mock_websocket,
            mock_user,
            "test-jti",
            {"type": "read", "chat_id": "not-a-uuid"},
        )

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Invalid chat_id" in msg["message"]
        mock_conn_manager.broadcast_to_chat.assert_not_called()


# ---------------------------------------------------------------------------
# get_online handler
# ---------------------------------------------------------------------------


class TestDispatchGetOnline:
    @pytest.mark.asyncio
    async def test_admin_gets_online_list(
        self, mock_websocket, admin_mock_user, mock_conn_manager
    ):
        online_ids = [uuid.uuid4(), uuid.uuid4()]
        checker = MagicMock(spec=PermissionChecker)
        checker.check_admin = AsyncMock(return_value=True)
        lifecycle = {"opened": 0, "closed": 0}
        container = _permission_container(checker, lifecycle)
        dispatcher = MessageDispatcher(mock_conn_manager, container=container)
        try:
            with patch.object(
                dispatcher, "_get_online_users_for_user", new_callable=AsyncMock
            ) as mock_get_online:
                mock_get_online.return_value = online_ids
                with patch("app.api.ws.dispatcher.audit_service"):
                    await dispatcher.dispatch(
                        mock_websocket,
                        admin_mock_user,
                        "test-jti",
                        {"type": "get_online"},
                    )
        finally:
            await container.close()

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "online_list"
        # RZ-33-08: UUIDs are now serialized to strings before send_json
        assert msg["users"] == [str(u) for u in online_ids]
        checker.check_admin.assert_awaited_once_with(
            str(admin_mock_user.id), user=admin_mock_user
        )
        assert lifecycle == {"opened": 1, "closed": 1}

    @pytest.mark.asyncio
    async def test_non_admin_denied(self, mock_websocket, mock_user, mock_conn_manager):
        checker = MagicMock(spec=PermissionChecker)
        checker.check_admin = AsyncMock(return_value=True)
        lifecycle = {"opened": 0, "closed": 0}
        container = _permission_container(checker, lifecycle)
        dispatcher = MessageDispatcher(mock_conn_manager, container=container)
        try:
            with patch("app.api.ws.dispatcher.audit_service") as mock_audit:
                await dispatcher.dispatch(
                    mock_websocket,
                    mock_user,
                    "test-jti",
                    {"type": "get_online"},
                )
        finally:
            await container.close()

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Access denied" in msg["message"]
        assert lifecycle == {"opened": 0, "closed": 0}
        checker.check_admin.assert_not_awaited()

        # Verify audit log
        mock_audit.log.assert_called()

    @pytest.mark.asyncio
    async def test_stale_admin_role_is_denied_by_spicedb(
        self, mock_websocket, admin_mock_user, mock_conn_manager
    ):
        checker = MagicMock(spec=PermissionChecker)
        checker.check_admin = AsyncMock(return_value=False)
        lifecycle = {"opened": 0, "closed": 0}
        container = _permission_container(checker, lifecycle)
        dispatcher = MessageDispatcher(mock_conn_manager, container=container)
        try:
            with (
                patch.object(
                    dispatcher, "_get_online_users_for_user", new_callable=AsyncMock
                ) as mock_get_online,
                patch("app.api.ws.dispatcher.audit_service") as mock_audit,
            ):
                await dispatcher.dispatch(
                    mock_websocket,
                    admin_mock_user,
                    "test-jti",
                    {"type": "get_online"},
                )
        finally:
            await container.close()

        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "error", "message": "Access denied"}
        )
        mock_get_online.assert_not_awaited()
        checker.check_admin.assert_awaited_once_with(
            str(admin_mock_user.id), user=admin_mock_user
        )
        assert lifecycle == {"opened": 1, "closed": 1}
        assert mock_audit.log.call_args.kwargs["reason"] == "admin_required"

    @pytest.mark.asyncio
    async def test_spicedb_unavailable_fails_closed_without_online_list(
        self, mock_websocket, admin_mock_user, mock_conn_manager
    ):
        checker = MagicMock(spec=PermissionChecker)
        checker.check_admin = AsyncMock(
            side_effect=SpiceDBUnavailableError("private transport detail")
        )
        lifecycle = {"opened": 0, "closed": 0}
        container = _permission_container(checker, lifecycle)
        dispatcher = MessageDispatcher(mock_conn_manager, container=container)
        try:
            with (
                patch.object(
                    dispatcher, "_get_online_users_for_user", new_callable=AsyncMock
                ) as mock_get_online,
                patch("app.api.ws.dispatcher.audit_service") as mock_audit,
            ):
                await dispatcher.dispatch(
                    mock_websocket,
                    admin_mock_user,
                    "test-jti",
                    {"type": "get_online"},
                )
        finally:
            await container.close()

        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "error", "message": "Authorization service unavailable"}
        )
        mock_get_online.assert_not_awaited()
        assert lifecycle == {"opened": 1, "closed": 1}
        assert mock_audit.log.call_args.kwargs["reason"] == "spicedb_unavailable"

    @pytest.mark.asyncio
    async def test_missing_app_container_fails_closed(
        self, mock_websocket, admin_mock_user, mock_conn_manager
    ):
        dispatcher = MessageDispatcher(mock_conn_manager)
        with (
            patch.object(
                dispatcher, "_get_online_users_for_user", new_callable=AsyncMock
            ) as mock_get_online,
            patch("app.api.ws.dispatcher.audit_service") as mock_audit,
        ):
            await dispatcher.dispatch(
                mock_websocket,
                admin_mock_user,
                "test-jti",
                {"type": "get_online"},
            )

        mock_websocket.send_json.assert_awaited_once_with(
            {"type": "error", "message": "Authorization service unavailable"}
        )
        mock_get_online.assert_not_awaited()
        assert mock_audit.log.call_args.kwargs["reason"] == "authorization_unavailable"

    @pytest.mark.asyncio
    async def test_ping_and_read_do_not_resolve_permission_checker(
        self, mock_websocket, mock_user, mock_conn_manager
    ):
        checker = MagicMock(spec=PermissionChecker)
        checker.check_admin = AsyncMock(return_value=True)
        lifecycle = {"opened": 0, "closed": 0}
        container = _permission_container(checker, lifecycle)
        dispatcher = MessageDispatcher(mock_conn_manager, container=container)
        try:
            with patch(
                "app.api.ws.dispatcher.update_last_seen",
                new_callable=AsyncMock,
                return_value=datetime.now(UTC),
            ):
                await dispatcher.dispatch(
                    mock_websocket, mock_user, "test-jti", {"type": "ping"}
                )
                await dispatcher.dispatch(
                    mock_websocket, mock_user, "test-jti", {"type": "read"}
                )
        finally:
            await container.close()

        checker.check_admin.assert_not_awaited()
        assert lifecycle == {"opened": 0, "closed": 0}


# ---------------------------------------------------------------------------
# unknown message type
# ---------------------------------------------------------------------------


class TestDispatchUnknown:
    @pytest.mark.asyncio
    async def test_unknown_type(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        await ws_dispatcher.dispatch(
            mock_websocket,
            mock_user,
            "test-jti",
            {"type": "some_random_type"},
        )

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Unknown message type" in msg["message"]

    @pytest.mark.asyncio
    async def test_none_type(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        await ws_dispatcher.dispatch(mock_websocket, mock_user, "test-jti", {})

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"


# ---------------------------------------------------------------------------
# helper methods
# ---------------------------------------------------------------------------


class TestDispatcherHelpers:
    @pytest.mark.asyncio
    async def test_get_online_users_for_user(self, ws_dispatcher, mock_conn_manager):
        user_id = uuid.uuid4()
        audience_list = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        audience = set(audience_list)

        with patch(
            "app.api.ws.presence._get_presence_audience",
            new_callable=AsyncMock,
            return_value=audience,
        ):
            # Only first 2 are online
            online_set = set(audience_list[:2])
            mock_conn_manager.is_online.side_effect = lambda uid: uid in online_set
            result = await ws_dispatcher._get_online_users_for_user(user_id)

        assert len(result) == 2

    def test_get_websocket_audit_context(self, ws_dispatcher, mock_websocket):
        ctx = ws_dispatcher._get_websocket_audit_context(mock_websocket)
        assert "ws_path" in ctx
        assert "ws_client" in ctx
        assert ctx["ws_client"] == "127.0.0.1"

    def test_audit_context_no_client(self, ws_dispatcher):
        ws = MagicMock()
        ws.client = None
        ws.url = MagicMock()
        ws.url.path = "/ws"

        ctx = ws_dispatcher._get_websocket_audit_context(ws)
        assert ctx["ws_client"] is None


@pytest.mark.asyncio
async def test_websocket_route_uses_app_container_per_get_online_frame() -> None:
    """The route passes its APP container; only get_online opens REQUEST scopes."""
    from app.api.websocket import websocket_chat

    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    checker = MagicMock(spec=PermissionChecker)
    checker.check_admin = AsyncMock(return_value=True)
    lifecycle = {"opened": 0, "closed": 0}
    container = _permission_container(checker, lifecycle)
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace(dishka_container=container))
    websocket.client = SimpleNamespace(host="127.0.0.1")
    websocket.url = SimpleNamespace(path="/ws/chat")
    websocket.receive_text = AsyncMock(
        side_effect=[
            '{"type":"ping"}',
            '{"type":"read"}',
            '{"type":"get_online"}',
            '{"type":"get_online"}',
            WebSocketDisconnect(code=1000),
        ]
    )
    online_ids = [uuid.uuid4()]
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.broadcast_presence = AsyncMock()
    manager.check_rate_limit.return_value = True
    manager.is_online.return_value = False
    last_seen = datetime.now(UTC)

    try:
        with (
            patch(
                "app.api.ws.authenticator.authenticator.authenticate_upgrade",
                new=AsyncMock(return_value=(user, "test-jti", None)),
            ),
            patch("app.api.websocket.manager", manager),
            patch(
                "app.api.websocket._resolve_user_from_ids",
                AsyncMock(return_value=(user, "test-jti")),
            ),
            patch("app.api.websocket.metrics.inc_ws_connections"),
            patch("app.api.websocket.metrics.dec_ws_connections"),
            patch(
                "app.api.websocket._update_last_seen",
                new=AsyncMock(return_value=last_seen),
            ),
            patch(
                "app.api.ws.dispatcher.update_last_seen",
                new=AsyncMock(return_value=last_seen),
            ),
            patch(
                "app.api.ws.dispatcher.MessageDispatcher._get_online_users_for_user",
                new=AsyncMock(return_value=online_ids),
            ),
            patch("app.api.ws.dispatcher.audit_service"),
        ):
            await websocket_chat(websocket)
    finally:
        await container.close()

    assert lifecycle == {"opened": 2, "closed": 2}
    assert checker.check_admin.await_count == 2
    online_frames = [
        call.args[0]
        for call in websocket.send_json.await_args_list
        if call.args[0].get("type") == "online_list"
    ]
    expected_frame = {
        "type": "online_list",
        "users": [str(user_id) for user_id in online_ids],
    }
    assert online_frames == [expected_frame, expected_frame]
    manager.disconnect.assert_awaited_once_with(websocket)
