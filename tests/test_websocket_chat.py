import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.api.ws.connection_manager import ConnectionManager
from app.core.config import settings
from app.models.chat import Chat, Message
from tests.fixtures.auth.auth_fixtures import create_access_token


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
        user_id = uuid.uuid4()

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
        user_id = uuid.uuid4()

        await connection_manager.connect(mock_ws1, user_id)
        await connection_manager.connect(mock_ws2, user_id)

        assert len(connection_manager.active_connections[user_id]) == 2
        assert mock_ws1 in connection_manager.active_connections[user_id]
        assert mock_ws2 in connection_manager.active_connections[user_id]

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(
        self, connection_manager: ConnectionManager
    ):
        """Test that disconnect properly removes user connection."""
        mock_ws = AsyncMock(spec=WebSocket)
        user_id = uuid.uuid4()

        # Manually add connection
        connection_manager.active_connections[user_id] = {mock_ws}
        connection_manager.connection_users[mock_ws] = user_id

        result = await connection_manager.disconnect(mock_ws)

        assert result == user_id
        assert user_id not in connection_manager.active_connections
        assert mock_ws not in connection_manager.connection_users

    @pytest.mark.asyncio
    async def test_disconnect_keeps_other_connections(
        self, connection_manager: ConnectionManager
    ):
        """Test that disconnect only removes the specific connection."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        user_id = uuid.uuid4()

        connection_manager.active_connections[user_id] = {mock_ws1, mock_ws2}
        connection_manager.connection_users[mock_ws1] = user_id
        connection_manager.connection_users[mock_ws2] = user_id

        await connection_manager.disconnect(mock_ws1)

        assert user_id in connection_manager.active_connections
        assert mock_ws2 in connection_manager.active_connections[user_id]
        assert len(connection_manager.active_connections[user_id]) == 1

    def test_is_online_returns_true_for_connected_user(
        self, connection_manager: ConnectionManager
    ):
        """Test is_online returns True when user has connections."""
        mock_ws = AsyncMock(spec=WebSocket)
        user_id = uuid.uuid4()
        connection_manager.active_connections[user_id] = {mock_ws}

        assert connection_manager.is_online(user_id) is True

    def test_is_online_returns_false_for_disconnected_user(
        self, connection_manager: ConnectionManager
    ):
        """Test is_online returns False when user has no connections."""
        assert connection_manager.is_online(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_send_to_user_delivers_message(
        self, connection_manager: ConnectionManager
    ):
        """Test that send_to_user delivers message to all user connections."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        user_id = uuid.uuid4()
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
        mock_ws1.send_json.side_effect = RuntimeError("Connection closed")
        user_id = uuid.uuid4()
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
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()

        connection_manager.active_connections = {
            uid1: {mock_ws1},
            uid2: {mock_ws2},
        }

        online = connection_manager.get_online_users()

        assert set(online) == {uid1, uid2}

    @pytest.mark.asyncio
    async def test_broadcast_presence_targets_chat_participants_only(
        self, connection_manager: ConnectionManager, db_session, user_factory
    ):
        """Presence updates should only go to users sharing a chat."""
        user_a = await user_factory()
        user_b = await user_factory()
        user_c = await user_factory()

        chat = Chat()
        chat.participants = [user_a, user_b]
        db_session.add(chat)
        await db_session.commit()

        ws_b = AsyncMock(spec=WebSocket)
        ws_c = AsyncMock(spec=WebSocket)
        connection_manager.active_connections[user_b.id] = {ws_b}
        connection_manager.connection_users[ws_b] = user_b.id
        connection_manager.active_connections[user_c.id] = {ws_c}
        connection_manager.connection_users[ws_c] = user_c.id

        last_seen = datetime.now(UTC)
        await connection_manager.broadcast_presence(
            user_a.id,
            True,
            last_seen,
            source="ping",
            force=True,
            publish=False,
        )

        ws_b.send_json.assert_called_once()
        ws_c.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_presence_throttles_pings(
        self, connection_manager: ConnectionManager, monkeypatch
    ):
        """Presence broadcasts should be throttled when configured."""
        send_mock = AsyncMock(return_value=1)
        monkeypatch.setattr(connection_manager, "send_to_user", send_mock)

        async def _audience(_user_id: uuid.UUID) -> set[uuid.UUID]:
            return {uuid.uuid4()}

        monkeypatch.setattr("app.api.ws.presence._get_presence_audience", _audience)
        monkeypatch.setattr(
            settings, "presence_ping_min_interval_seconds", 60, raising=False
        )

        curr_user_id = uuid.uuid4()
        last_seen = datetime.now(UTC)
        await connection_manager.broadcast_presence(
            curr_user_id,
            True,
            last_seen,
            source="ping",
            publish=False,
        )
        await connection_manager.broadcast_presence(
            curr_user_id,
            True,
            last_seen,
            source="ping",
            publish=False,
        )

        assert send_mock.call_count == 1


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
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, patch

        from app.api.ws.auth import get_user_from_token

        user = await user_factory(full_name="Test User")
        token, _ = await create_access_token(str(user.id), db=db_session)
        await db_session.commit()

        # Mock Redis (unavailable in tests) and use test DB session
        @asynccontextmanager
        async def _mock_session():
            yield db_session

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)

        with (
            patch(
                "app.deps.cache.get_cache_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("app.api.ws.auth.async_session", side_effect=_mock_session),
        ):
            result_user, session_jti = await get_user_from_token(token)

        assert result_user is not None
        assert result_user.id == user.id
        assert session_jti is not None

    @pytest.mark.asyncio
    async def test_get_user_from_token_invalid(self):
        """Test invalid token returns None."""
        from app.api.ws.auth import get_user_from_token

        result_user, session_jti = await get_user_from_token("invalid-token")

        assert result_user is None
        assert session_jti is None

    @pytest.mark.asyncio
    async def test_get_user_from_token_inactive_user(self, db_session, user_factory):
        """Test inactive user returns None."""
        from app.api.ws.auth import get_user_from_token

        user = await user_factory(is_active=False)
        token, _ = await create_access_token(str(user.id), db=db_session)

        result_user, _session_jti = await get_user_from_token(token)

        assert result_user is None


class TestMessageSerialization:
    """Tests for message serialization."""

    @pytest.mark.asyncio
    async def test_serialize_message(self, db_session, user_factory):
        """Test message serialization includes all fields."""
        from app.api.ws.serializers import serialize_message

        user = await user_factory(full_name="Test User")

        chat = Chat(id=uuid.uuid4())
        db_session.add(chat)
        await db_session.commit()

        message = Message(
            id=uuid.uuid4(),
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

        assert result["id"] == message.id
        assert result["chat_id"] == chat.id
        assert result["sender_id"] == user.id
        assert result["content"] == "Hello!"
        assert result["read_status"] is False
        assert result["sender"] is not None
        assert "attachments" in result

    @pytest.mark.asyncio
    async def test_serialize_message_with_presence(self, db_session, user_factory):
        """Test message serialization with sender presence info."""
        from app.api.ws.serializers import serialize_message
        from app.schemas.chat import PresenceStatus

        user = await user_factory(full_name="Test User")

        chat = Chat(id=uuid.uuid4())
        db_session.add(chat)
        await db_session.commit()

        message = Message(
            id=uuid.uuid4(),
            chat_id=chat.id,
            sender_id=user.id,
            content="Hello!",
            created_at=datetime.now(UTC),
            read_status=False,
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        message.sender = user

        # Test presence matching
        status = PresenceStatus(active=True, last_seen_at=datetime.now(UTC))
        presence = {user.id: status}
        result = serialize_message(message, presence=presence)

        assert result["sender_presence"] is not None
        assert result["sender_presence"]["active"] is True
        assert (
            result["sender_presence"]["last_seen_at"] == status.last_seen_at.isoformat()
        )

        # Test presence missing matching user
        presence_other = {uuid.uuid4(): status}
        result_other = serialize_message(message, presence=presence_other)
        assert result_other["sender_presence"] is None
