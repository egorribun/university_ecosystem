"""Behavioral coverage closure for WebSocket connection management."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket


@pytest.mark.asyncio
async def test_rate_limiter_refills_and_rejects_when_empty() -> None:
    from app.api.ws import connection_manager as module

    limiter = module.WebSocketRateLimiter(rate=1.0, capacity=1.0)
    loop = SimpleNamespace(time=MagicMock(side_effect=[100.0, 100.0, 101.0]))
    with patch.object(module.asyncio, "get_running_loop", return_value=loop):
        assert limiter.consume() is True
        assert limiter.consume() is False
        assert limiter.consume() is True


@pytest.mark.asyncio
async def test_lazy_semaphores_reuse_and_cleanup_stale_rooms() -> None:
    from app.api.ws import connection_manager as module

    module._PRESENCE_SEMAPHORE = None
    assert module._get_presence_semaphore() is module._get_presence_semaphore()

    module._room_semaphores.clear()
    module._room_semaphores_lock = None
    room_lock = module._get_room_semaphores_lock()
    assert module._get_room_semaphores_lock() is room_lock
    first = await module._get_room_semaphore("room-a")
    assert await module._get_room_semaphore("room-a") is first

    raced = object()

    class LockThatPopulatesRoom:
        async def __aenter__(self):
            module._room_semaphores["room-raced"] = raced
            return self

        async def __aexit__(self, *_args):
            return None

    module._room_semaphores.pop("room-raced", None)
    with patch.object(
        module,
        "_get_room_semaphores_lock",
        return_value=LockThatPopulatesRoom(),
    ):
        assert await module._get_room_semaphore("room-raced") is raced

    await module.cleanup_room_semaphores({"room-a"})
    assert "room-raced" not in module._room_semaphores
    await module.cleanup_room_semaphores(set(module._room_semaphores))
    module._room_semaphores.clear()


@pytest.mark.asyncio
async def test_connect_subprotocol_and_per_user_limit() -> None:
    from app.api.ws import connection_manager as module

    settings = SimpleNamespace(
        ws_max_connections_per_user=1,
        ws_message_rate=2.0,
        ws_message_burst=3.0,
    )
    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    first = AsyncMock(spec=WebSocket)
    second = AsyncMock(spec=WebSocket)
    with patch.object(module, "settings", settings):
        assert (
            await manager.connect(
                first, user_id, session_jti="session", subprotocol="chat.v1"
            )
            is True
        )
        assert await manager.connect(second, user_id, session_jti="session") is False
    first.accept.assert_awaited_once_with(subprotocol="chat.v1")
    second.close.assert_awaited_once_with(code=1008, reason="Connection limit exceeded")


@pytest.mark.asyncio
async def test_disconnect_unknown_and_rate_limit_lookup_paths() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    websocket = AsyncMock(spec=WebSocket)
    assert await manager.disconnect(websocket) is None
    assert manager.check_rate_limit(websocket) is True
    limiter = MagicMock()
    limiter.consume.side_effect = [False, True]
    manager.rate_limiters[websocket] = limiter
    assert manager.check_rate_limit(websocket) is False
    assert manager.check_rate_limit(websocket) is True


@pytest.mark.asyncio
async def test_send_to_user_empty_and_unmapped_dead_connection() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    assert await manager.send_to_user(user_id, {"type": "empty"}) == 0

    dead = AsyncMock(spec=WebSocket)
    dead.send_json.side_effect = RuntimeError("closed")
    manager.active_connections[user_id] = {dead}
    manager.connection_sessions[dead] = "session"
    with patch.object(
        module, "_resolve_user_from_ids", AsyncMock(return_value=(object(), "session"))
    ):
        assert await manager.send_to_user(user_id, {"type": "dead"}) == 0
    assert dead not in manager.rate_limiters


@pytest.mark.asyncio
async def test_participants_are_reloaded_for_every_broadcast() -> None:
    from app.api.ws import connection_manager as module

    chat_id = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()
    repo = MagicMock()
    repo.get_participants = AsyncMock(side_effect=[[first], [second]])

    @asynccontextmanager
    async def session():
        yield object()

    manager = module.ConnectionManager(session_factory=session)
    with patch.object(module, "ChatRepository", return_value=repo):
        assert await manager._get_chat_participants(chat_id) == [first]
        assert await manager._get_chat_participants(chat_id) == [second]
    assert repo.get_participants.await_count == 2


@pytest.mark.asyncio
async def test_participant_lookup_uses_injected_session_factory() -> None:
    from app.api.ws import connection_manager as module

    chat_id = uuid.uuid4()
    participants = [uuid.uuid4(), uuid.uuid4()]
    repo = MagicMock()
    repo.get_participants = AsyncMock(return_value=participants)

    @asynccontextmanager
    async def invalid_context():
        yield MagicMock()

    class Factory:
        def __call__(self):
            return invalid_context()

    manager = module.ConnectionManager(session_factory=Factory())
    with patch.object(module, "ChatRepository", return_value=repo):
        result = await manager._get_chat_participants(chat_id)
    assert result == participants
    repo.get_participants.assert_awaited_once_with(chat_id)


@pytest.mark.asyncio
async def test_participant_lookup_uses_global_factory_fallback() -> None:
    from app.api.ws import connection_manager as module

    chat_id = uuid.uuid4()
    participants = [uuid.uuid4()]
    repo = MagicMock()
    repo.get_participants = AsyncMock(return_value=participants)

    class SessionFactory:
        def __call__(self):
            class Context:
                async def __aenter__(self):
                    return MagicMock()

                async def __aexit__(self, *_args):
                    return None

            return Context()

    manager = module.ConnectionManager()
    with (
        patch.object(module, "ChatRepository", return_value=repo),
        patch("app.core.database.async_session", new=SessionFactory()),
    ):
        result = await manager._get_chat_participants(chat_id)
    assert result == participants


@pytest.mark.asyncio
async def test_broadcast_to_chat_excludes_sender_and_mirrors_to_nats() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    chat_id = uuid.uuid4()
    sender = uuid.uuid4()
    recipient = uuid.uuid4()
    manager._get_chat_participants = AsyncMock(return_value=[sender, recipient])
    manager.send_to_user = AsyncMock(return_value=1)
    broker = SimpleNamespace(publish_core=AsyncMock())
    message = {"type": "chat.message", "text": "hello"}
    module._room_semaphores.clear()
    with patch("app.core.nats_broker.broker", broker):
        sent = await manager.broadcast_to_chat(chat_id, message, exclude_user_id=sender)
    assert sent == 1
    manager.send_to_user.assert_awaited_once_with(recipient, message)
    broker.publish_core.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_to_chat_keeps_local_delivery_when_nats_fails() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    chat_id = uuid.uuid4()
    recipient = uuid.uuid4()
    manager._get_chat_participants = AsyncMock(return_value=[recipient])
    manager.send_to_user = AsyncMock(return_value=2)
    broker = SimpleNamespace(
        publish_core=AsyncMock(side_effect=ConnectionError("down"))
    )
    with patch("app.core.nats_broker.broker", broker):
        assert await manager.broadcast_to_chat(chat_id, {"type": "message"}) == 2


@pytest.mark.asyncio
async def test_broadcast_to_chat_can_propagate_nats_failure_for_outbox_retry() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    chat_id = uuid.uuid4()
    recipient = uuid.uuid4()
    manager._get_chat_participants = AsyncMock(return_value=[recipient])
    manager.send_to_user = AsyncMock(return_value=1)
    broker = SimpleNamespace(
        publish_core=AsyncMock(side_effect=ConnectionError("nats unavailable"))
    )

    with (
        patch("app.core.nats_broker.broker", broker),
        pytest.raises(ConnectionError, match="nats unavailable"),
    ):
        await manager.broadcast_to_chat(
            chat_id,
            {"type": "message_edited", "room": str(chat_id)},
            propagate_nats_failure=True,
        )

    manager.send_to_user.assert_awaited_once_with(
        recipient, {"type": "message_edited", "room": str(chat_id)}
    )


def test_presence_throttle_decision_matrix() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    with patch.object(
        module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=10)
    ):
        assert manager._should_broadcast_presence(user_id, now, force=False) is True
        manager._last_presence_sent_at[user_id] = now
        assert manager._should_broadcast_presence(user_id, now, force=False) is False
        manager._last_presence_sent_at[user_id] = now - timedelta(seconds=11)
        assert manager._should_broadcast_presence(user_id, now, force=False) is True
        assert manager._should_broadcast_presence(user_id, now, force=True) is True

    with patch.object(
        module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=-1)
    ):
        assert manager._should_broadcast_presence(user_id, now, force=False) is True


@pytest.mark.asyncio
async def test_broadcast_presence_publishes_and_fans_out() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    recipient = uuid.uuid4()
    manager.send_to_user = AsyncMock(return_value=1)
    pubsub = SimpleNamespace(publish=AsyncMock())
    with (
        patch.object(
            module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=0)
        ),
        patch(
            "app.api.ws.presence._get_presence_audience",
            new=AsyncMock(return_value={recipient}),
        ),
        patch("app.api.ws.presence.presence_pubsub", pubsub),
        patch.object(module, "record_presence_event") as event,
    ):
        result = await manager.broadcast_presence(
            user_id,
            True,
            datetime.now(UTC),
            source="test",
        )
    assert result == 1
    pubsub.publish.assert_awaited_once()
    event.assert_called_once_with("active", "test")


@pytest.mark.asyncio
async def test_broadcast_presence_throttle_and_empty_audience() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    manager._last_presence_sent_at[user_id] = datetime.now(UTC)
    with (
        patch.object(
            module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=60)
        ),
        patch.object(module, "record_presence_throttled") as throttled,
        patch(
            "app.api.ws.presence._get_presence_audience", new=AsyncMock()
        ) as audience,
    ):
        assert (
            await manager.broadcast_presence(
                user_id, False, None, source="test", publish=False
            )
            == 0
        )
    throttled.assert_called_once_with("inactive", "test")
    audience.assert_not_awaited()

    with (
        patch.object(
            module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=0)
        ),
        patch(
            "app.api.ws.presence._get_presence_audience",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "app.api.ws.presence.presence_pubsub",
            SimpleNamespace(publish=AsyncMock()),
        ),
    ):
        assert (
            await manager.broadcast_presence(user_id, False, None, source="test") == 0
        )


@pytest.mark.asyncio
async def test_broadcast_presence_can_skip_pubsub_publish() -> None:
    from app.api.ws import connection_manager as module

    manager = module.ConnectionManager()
    user_id = uuid.uuid4()
    recipient = uuid.uuid4()
    manager.send_to_user = AsyncMock(return_value=1)
    pubsub = SimpleNamespace(publish=AsyncMock())
    with (
        patch.object(
            module, "settings", SimpleNamespace(presence_ping_min_interval_seconds=0)
        ),
        patch(
            "app.api.ws.presence._get_presence_audience",
            new=AsyncMock(return_value={recipient}),
        ),
        patch("app.api.ws.presence.presence_pubsub", pubsub),
    ):
        assert (
            await manager.broadcast_presence(
                user_id, True, None, source="test", publish=False
            )
            == 1
        )
    pubsub.publish.assert_not_awaited()


def test_connection_manager_dependency_prefers_app_state_then_global() -> None:
    from app.api.ws import connection_manager as module

    app_manager = object()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(connection_manager=app_manager))
    )
    assert module.get_connection_manager(request) is app_manager
    fallback_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert module.get_connection_manager(fallback_request) is module.manager


@pytest.mark.asyncio
async def test_outbox_broadcast_propagates_nats_disconnect() -> None:
    from app.api.ws import connection_manager as module
    from app.core.nats_broker import NatsTaskBroker

    manager = module.ConnectionManager()
    chat_id = uuid.uuid4()
    recipient = uuid.uuid4()
    participant_lookup = AsyncMock(return_value=[recipient])
    local_send = AsyncMock(return_value=1)
    broker = NatsTaskBroker()
    assert broker._nc is None

    with (
        patch.object(manager, "_get_chat_participants", participant_lookup),
        patch.object(manager, "send_to_user", local_send),
        patch("app.core.nats_broker.broker", broker),
        pytest.raises(ConnectionError),
    ):
        await manager.broadcast_to_chat(
            chat_id,
            {"type": "message_edited", "room": str(chat_id)},
            propagate_nats_failure=True,
        )

    local_send.assert_awaited_once_with(
        recipient, {"type": "message_edited", "room": str(chat_id)}
    )
