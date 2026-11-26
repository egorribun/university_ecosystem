import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket

from app.api.ws import connection_manager as module


@pytest.mark.asyncio
async def test_connection_lifecycle_logs_omit_user_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    first = AsyncMock(spec=WebSocket)
    second = AsyncMock(spec=WebSocket)
    caplog.set_level(logging.INFO, logger=module.__name__)
    settings = SimpleNamespace(
        ws_max_connections_per_user=1,
        ws_message_rate=2.0,
        ws_message_burst=3.0,
    )

    with patch.object(module, "settings", settings):
        assert await manager.connect(first, user_id, session_jti="demo-session")
        assert not await manager.connect(second, user_id, session_jti="demo-session")
        assert await manager.disconnect(first) == user_id

    assert "ws_connected" in caplog.text
    assert "ws_connection_limit_reached" in caplog.text
    assert "'current': 1" in caplog.text
    assert "'limit': 1" in caplog.text
    assert "ws_disconnected" in caplog.text
    assert str(user_id) not in caplog.text


@pytest.mark.asyncio
async def test_send_failure_logs_keep_error_class_and_remove_dead_connection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    websocket = AsyncMock(spec=WebSocket)
    detail = "private-transport-diagnostic"
    websocket.send_json.side_effect = RuntimeError(detail)
    assert await manager.connect(websocket, user_id, session_jti="demo-session")
    caplog.clear()
    caplog.set_level(logging.INFO, logger=module.__name__)

    with patch.object(
        module, "_resolve_user_from_ids", new=AsyncMock(return_value=(object(), None))
    ):
        assert await manager.send_to_user(user_id, {"type": "demo"}) == 0

    assert not manager.is_online(user_id)
    assert "ws_send_failed" in caplog.text
    assert "ws_batch_disconnected" in caplog.text
    assert str(user_id) not in caplog.text
    assert detail not in caplog.text
    assert "RuntimeError" in caplog.text
