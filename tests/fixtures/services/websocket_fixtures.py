"""Fixtures for WebSocket dispatcher, presence, and auth tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.ws.dispatcher import MessageDispatcher


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Mock WebSocket with send_json, receive_json, close, and client."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock(return_value={})
    ws.close = AsyncMock()
    # Simulate client info
    client = MagicMock()
    client.host = "127.0.0.1"
    ws.client = client
    ws.url = MagicMock()
    ws.url.path = "/ws"
    return ws


@pytest.fixture
def mock_conn_manager() -> MagicMock:
    """Mock ConnectionManager with broadcast/presence methods."""
    manager = MagicMock()
    manager.broadcast_presence = AsyncMock()
    manager.broadcast_to_chat = AsyncMock()
    manager.send_to_user = AsyncMock()
    manager.is_online = MagicMock(return_value=True)
    return manager


@pytest.fixture
def mock_user() -> MagicMock:
    """Mock User with id, email, role, profile."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = "student"
    user.profile = MagicMock()
    user.profile.full_name = "Test User"
    return user


@pytest.fixture
def admin_mock_user() -> MagicMock:
    """Mock admin User."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.role = "admin"
    user.profile = MagicMock()
    user.profile.full_name = "Admin User"
    return user


@pytest.fixture
def ws_dispatcher(mock_conn_manager: MagicMock) -> MessageDispatcher:
    """Pre-wired MessageDispatcher with mocked manager."""
    return MessageDispatcher(manager=mock_conn_manager)
