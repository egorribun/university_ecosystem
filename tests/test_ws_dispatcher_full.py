"""Comprehensive tests for app/api/ws/dispatcher.py — MessageDispatcher.

Covers direct-backend message types: ping, legacy read, get_online, unknown.
Tests participant validation, admin checks, error handling, and audit logging.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        self, ws_dispatcher, mock_websocket, admin_mock_user, mock_conn_manager
    ):
        online_ids = [uuid.uuid4(), uuid.uuid4()]
        with patch.object(
            ws_dispatcher, "_get_online_users_for_user", new_callable=AsyncMock
        ) as mock_get_online:
            mock_get_online.return_value = online_ids
            with patch("app.api.ws.dispatcher.audit_service"):
                await ws_dispatcher.dispatch(
                    mock_websocket,
                    admin_mock_user,
                    "test-jti",
                    {"type": "get_online"},
                )

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "online_list"
        # RZ-33-08: UUIDs are now serialized to strings before send_json
        assert msg["users"] == [str(u) for u in online_ids]

    @pytest.mark.asyncio
    async def test_non_admin_denied(
        self, ws_dispatcher, mock_websocket, mock_user, mock_conn_manager
    ):
        with patch("app.api.ws.dispatcher.audit_service") as mock_audit:
            await ws_dispatcher.dispatch(
                mock_websocket,
                mock_user,
                "test-jti",
                {"type": "get_online"},
            )

        mock_websocket.send_json.assert_called_once()
        msg = mock_websocket.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Access denied" in msg["message"]

        # Verify audit log
        mock_audit.log.assert_called()


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
