"""Focused lifecycle contracts for the WebSocket connection manager."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket


@pytest.mark.asyncio
async def test_concurrent_connects_cannot_bypass_per_user_connection_limit() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    first = AsyncMock(spec=WebSocket)
    second = AsyncMock(spec=WebSocket)
    first_accept_started = asyncio.Event()
    release_first_accept = asyncio.Event()
    second_connect_started = asyncio.Event()

    async def hold_first_accept(**_kwargs: object) -> None:
        first_accept_started.set()
        await release_first_accept.wait()

    async def connect_second() -> bool:
        second_connect_started.set()
        return await manager.connect(second, user_id)

    first.accept.side_effect = hold_first_accept
    settings = SimpleNamespace(
        ws_max_connections_per_user=1,
        ws_message_rate=2.0,
        ws_message_burst=3.0,
    )

    with patch.object(module, "settings", settings):
        first_task = asyncio.create_task(manager.connect(first, user_id))
        await first_accept_started.wait()
        second_task = asyncio.create_task(connect_second())
        await second_connect_started.wait()

        try:
            # The first socket is suspended inside accept while holding the
            # manager lock; the competing socket must not be accepted yet.
            assert manager._lock.locked()
            second.accept.assert_not_awaited()
        finally:
            release_first_accept.set()
            first_result, second_result = await asyncio.gather(
                first_task, second_task, return_exceptions=True
            )

    assert first_result is True
    assert second_result is False
    first.accept.assert_awaited_once_with()
    second.accept.assert_not_awaited()
    second.close.assert_awaited_once_with(code=1008, reason="Connection limit exceeded")
    assert manager.active_connections == {user_id: {first}}
    assert manager.connection_users == {first: user_id}
    assert set(manager.rate_limiters) == {first}
