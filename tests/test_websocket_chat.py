"""Tests for WebSocket chat functionality."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.api.websocket import ConnectionManager
from app.auth.security import create_access_token
from app.models.chat import Chat, Message


@pytest.fixture
def connection_manager() -> ConnectionManager:
    """Create a fresh ConnectionManager for testing."""
    return ConnectionManager()


class TestConnectionManager:
    """Tests for ConnectionManager class."""

    @pytest.mark.asyncio
    async def test_connect_registers_user(self, connection_manager: ConnectionManager):
        """Test that connect properly registers user connection."""
        mock_ws = AsyncMock(spec=WebSocket)
        user_id = 1

        await connection_manager.connect(mock_ws, user_id)

        assert user_id in connection_manager.active_connections
        assert mock_ws in connection_manager.active_connections[user_id]
        assert connection_manager.connection_users[mock_ws] == user_id
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_multiple_connections_same_user(
        self, connection_manager: ConnectionManager
    ):
        """Test that user can have multiple connections (tabs/devices)."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        user_id = 1

        await connection_manager.connect(mock_ws1, user_id)
        await connection_manager.connect(mock_ws2, user_id)

        assert len(connection_manager.active_connections[user_id]) == 2
        assert mock_ws1 in connection_manager.active_connections[user_id]
        assert mock_ws2 in connection_manager.active_connections[user_id]

    def test_disconnect_removes_connection(self, connection_manager: ConnectionManager):
        """Test that disconnect properly removes user connection."""
        mock_ws = AsyncMock(spec=WebSocket)
        user_id = 1

        # Manually add connection
        connection_manager.active_connections[user_id] = {mock_ws}
        connection_manager.connection_users[mock_ws] = user_id

        result = connection_manager.disconnect(mock_ws)

        assert result == user_id
        assert user_id not in connection_manager.active_connections
        assert mock_ws not in connection_manager.connection_users

    def test_disconnect_keeps_other_connections(
        self, connection_manager: ConnectionManager
    ):
        """Test that disconnect only removes the specific connection."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        user_id = 1

        connection_manager.active_connections[user_id] = {mock_ws1, mock_ws2}
        connection_manager.connection_users[mock_ws1] = user_id
        connection_manager.connection_users[mock_ws2] = user_id

        connection_manager.disconnect(mock_ws1)

        assert user_id in connection_manager.active_connections
        assert mock_ws2 in connection_manager.active_connections[user_id]
        assert len(connection_manager.active_connections[user_id]) == 1

    def test_is_online_returns_true_for_connected_user(
        self, connection_manager: ConnectionManager
    ):
        """Test is_online returns True when user has connections."""
        mock_ws = AsyncMock(spec=WebSocket)
        user_id = 1
        connection_manager.active_connections[user_id] = {mock_ws}

        assert connection_manager.is_online(user_id) is True

    def test_is_online_returns_false_for_disconnected_user(
        self, connection_manager: ConnectionManager
    ):
        """Test is_online returns False when user has no connections."""
        assert connection_manager.is_online(999) is False

    @pytest.mark.asyncio
    async def test_send_to_user_delivers_message(
        self, connection_manager: ConnectionManager
    ):
        """Test that send_to_user delivers message to all user connections."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        user_id = 1
        message = {"type": "test", "data": "hello"}

        connection_manager.active_connections[user_id] = {mock_ws1, mock_ws2}
        connection_manager.connection_users[mock_ws1] = user_id
        connection_manager.connection_users[mock_ws2] = user_id

        sent = await connection_manager.send_to_user(user_id, message)

        assert sent == 2
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_user_handles_dead_connections(
        self, connection_manager: ConnectionManager
    ):
        """Test that dead connections are cleaned up on send failure."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        mock_ws1.send_json.side_effect = Exception("Connection closed")
        user_id = 1
        message = {"type": "test"}

        connection_manager.active_connections[user_id] = {mock_ws1, mock_ws2}
        connection_manager.connection_users[mock_ws1] = user_id
        connection_manager.connection_users[mock_ws2] = user_id

        sent = await connection_manager.send_to_user(user_id, message)

        assert sent == 1  # Only ws2 succeeded
        assert mock_ws1 not in connection_manager.connection_users

    def test_get_online_users(self, connection_manager: ConnectionManager):
        """Test get_online_users returns all connected user IDs."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)

        connection_manager.active_connections = {
            1: {mock_ws1},
            2: {mock_ws2},
        }

        online = connection_manager.get_online_users()

        assert set(online) == {1, 2}


class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    def test_websocket_requires_auth(self, app):
        """Test that WebSocket requires authentication."""
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/chat"):
                pass
        assert exc.value.code in (1008, 4001)

    @pytest.mark.asyncio
    async def test_get_user_from_token_valid(self, db_session, user_factory):
        """Test token validation returns user."""
        from app.api.websocket import get_user_from_token

        user = await user_factory(full_name="Test User")
        token, _ = await create_access_token(str(user.id), db=db_session)
        await db_session.commit()

        result_user, session_jti = await get_user_from_token(token)

        assert result_user is not None
        assert result_user.id == user.id
        assert session_jti is not None

    @pytest.mark.asyncio
    async def test_get_user_from_token_invalid(self):
        """Test invalid token returns None."""
        from app.api.websocket import get_user_from_token

        result_user, session_jti = await get_user_from_token("invalid-token")

        assert result_user is None
        assert session_jti is None

    @pytest.mark.asyncio
    async def test_get_user_from_token_inactive_user(self, db_session, user_factory):
        """Test inactive user returns None."""
        from app.api.websocket import get_user_from_token

        user = await user_factory(is_active=False)
        token = await create_access_token(str(user.id))

        result_user, session_jti = await get_user_from_token(token)

        assert result_user is None


class TestMessageSerialization:
    """Tests for message serialization."""

    @pytest.mark.asyncio
    async def test_serialize_message(self, db_session, user_factory):
        """Test message serialization includes all fields."""
        from app.api.websocket import serialize_message

        user = await user_factory(full_name="Test User")

        chat = Chat(id="test-chat")
        db_session.add(chat)
        await db_session.commit()

        message = Message(
            id="msg-1",
            chat_id=chat.id,
            sender_id=user.id,
            content="Hello!",
            created_at=datetime.now(UTC),
            read_status=False,
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # Load sender relationship
        message.sender = user

        result = serialize_message(message)

        assert result["id"] == "msg-1"
        assert result["chat_id"] == chat.id
        assert result["sender_id"] == user.id
        assert result["content"] == "Hello!"
        assert result["read_status"] is False
        assert result["sender"] is not None
        assert "attachments" in result
