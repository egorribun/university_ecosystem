"""Behavioral coverage closure for presence cache and pub/sub flows."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_presence_audience_ignores_redis_cache_hit() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()
    audience = {uuid.uuid4(), uuid.uuid4()}
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = SimpleNamespace(payload=list(audience))
    repo = MagicMock(get_presence_audience=AsyncMock(return_value=set()))

    @asynccontextmanager
    async def session_context():
        yield MagicMock()

    with (
        patch.object(presence, "get_cache", return_value=cache),
        patch.object(presence, "ChatRepository", return_value=repo),
        patch.object(presence, "async_session", session_context),
    ):
        result = await presence._get_presence_audience(user_id)
    assert result == set()
    cache.get.assert_not_awaited()
    cache.set.assert_not_awaited()
    repo.get_presence_audience.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_presence_audience_reloads_database_each_time() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()
    first, second = {uuid.uuid4()}, {uuid.uuid4()}
    repo = MagicMock()
    repo.get_presence_audience = AsyncMock(side_effect=[first, second])

    @asynccontextmanager
    async def session_context():
        yield MagicMock()

    with (
        patch.object(presence, "ChatRepository", return_value=repo),
        patch.object(presence, "async_session", session_context),
    ):
        assert await presence._get_presence_audience(user_id) == first
        assert await presence._get_presence_audience(user_id) == second
    assert repo.get_presence_audience.await_count == 2


@pytest.mark.asyncio
async def test_presence_audience_session_failure_is_not_suppressed() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()

    async def fail_session():
        raise OSError("owned database outage")

    @asynccontextmanager
    async def session_context():
        yield await fail_session()

    with patch.object(presence, "async_session", session_context):
        with pytest.raises(OSError, match="owned database outage"):
            await presence._get_presence_audience(user_id)


@pytest.mark.asyncio
async def test_presence_audience_query_failure_is_not_suppressed() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_presence_audience = AsyncMock(side_effect=OSError("owned query outage"))

    @asynccontextmanager
    async def session_context():
        yield MagicMock()

    with (
        patch.object(presence, "ChatRepository", return_value=repo),
        patch.object(presence, "async_session", session_context),
    ):
        with pytest.raises(OSError, match="owned query outage"):
            await presence._get_presence_audience(user_id)


@pytest.mark.asyncio
async def test_presence_pubsub_initialize_from_shared_redis_and_fallback() -> None:
    from app.api.ws import presence

    fake_task = MagicMock()

    def create_task_without_running(coro):
        coro.close()
        return fake_task

    redis = AsyncMock()
    settings = SimpleNamespace(
        presence_pubsub_enabled=True,
        cache_redis_url="redis://presence",
        presence_pubsub_channel="presence:updates",
        redis_pool_size=4,
    )
    with (
        patch.object(presence, "settings", settings),
        patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)),
        patch.object(
            presence.asyncio,
            "create_task",
            side_effect=create_task_without_running,
        ),
    ):
        pubsub = presence.PresencePubSub()
        await pubsub.initialize()
    assert pubsub._redis is redis
    assert pubsub._pubsub_task is fake_task

    fallback_redis = AsyncMock()
    with (
        patch.object(presence, "settings", settings),
        patch(
            "app.deps.cache.get_cache_client",
            new=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch.object(
            presence.Redis, "from_url", return_value=fallback_redis
        ) as from_url,
        patch.object(
            presence.asyncio,
            "create_task",
            side_effect=create_task_without_running,
        ),
    ):
        fallback = presence.PresencePubSub()
        await fallback.initialize()
    assert fallback._redis is fallback_redis
    from_url.assert_called_once_with(
        "redis://presence", decode_responses=True, max_connections=4
    )


@pytest.mark.asyncio
async def test_presence_pubsub_initialize_without_redis_does_not_start_listener() -> (
    None
):
    from app.api.ws import presence

    settings = SimpleNamespace(
        presence_pubsub_enabled=True,
        cache_redis_url="",
        presence_pubsub_channel="presence:updates",
    )
    get_cache_client = AsyncMock()
    with (
        patch.object(presence, "settings", settings),
        patch("app.deps.cache.get_cache_client", new=get_cache_client),
        patch.object(presence.Redis, "from_url") as from_url,
        patch.object(presence.asyncio, "create_task") as create_task,
    ):
        pubsub = presence.PresencePubSub()
        await pubsub.initialize()
    assert pubsub._redis is None
    assert pubsub._pubsub_task is None
    get_cache_client.assert_not_awaited()
    from_url.assert_not_called()
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_presence_listener_processes_messages_and_cancellation() -> None:
    from app.api.ws import presence

    channel = "presence:updates"
    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock()
    pubsub_client.unsubscribe = AsyncMock()
    pubsub_client.close = AsyncMock()
    instance_id = presence._PRESENCE_INSTANCE_ID
    user_id = str(uuid.uuid4())

    async def messages():
        yield {"type": "subscribe", "data": "ignored"}
        yield {"type": "message", "data": "not-json"}
        yield {
            "type": "message",
            "data": json.dumps({"instance_id": instance_id}),
        }
        yield {
            "type": "message",
            "data": json.dumps({"user_id": user_id, "active": True}),
        }
        raise asyncio.CancelledError

    pubsub_client.listen.return_value = messages()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    settings = SimpleNamespace(presence_pubsub_channel=channel)
    listener = presence.PresencePubSub()
    listener._redis = redis
    with (
        patch.object(presence, "settings", settings),
        patch.object(presence, "_handle_presence_pubsub", new=AsyncMock()) as handle,
    ):
        await listener._listen_for_updates()
    pubsub_client.subscribe.assert_awaited_once_with(channel)
    pubsub_client.unsubscribe.assert_awaited_once_with(channel)
    pubsub_client.close.assert_awaited_once()
    handle.assert_awaited_once_with({"user_id": user_id, "active": True})


@pytest.mark.asyncio
async def test_presence_listener_handles_no_redis_and_connection_error() -> None:
    from app.api.ws import presence

    no_redis_listener = presence.PresencePubSub()
    no_redis_handler = AsyncMock()
    with patch.object(presence, "_handle_presence_pubsub", new=no_redis_handler):
        await no_redis_listener._listen_for_updates()
    assert no_redis_listener._redis is None
    no_redis_handler.assert_not_awaited()

    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock()
    pubsub_client.unsubscribe = AsyncMock()
    pubsub_client.close = AsyncMock()

    async def failing_messages():
        raise ConnectionError("pubsub disconnected")
        yield  # pragma: no cover

    pubsub_client.listen.return_value = failing_messages()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis
    with patch.object(
        presence, "settings", SimpleNamespace(presence_pubsub_channel="presence")
    ):
        await listener._listen_for_updates()
    redis.pubsub.assert_called_once_with()
    pubsub_client.subscribe.assert_awaited_once_with("presence")
    pubsub_client.close.assert_awaited_once_with()
    pubsub_client.unsubscribe.assert_not_awaited()

    normal_ps = MagicMock()
    normal_ps.subscribe = AsyncMock()
    normal_ps.unsubscribe = AsyncMock()
    normal_ps.close = AsyncMock()
    normal_messages_seen = []

    async def normal_messages():
        normal_messages_seen.append("subscribe")
        yield {"type": "subscribe"}

    normal_ps.listen.return_value = normal_messages()
    normal_redis = MagicMock()
    normal_redis.pubsub.return_value = normal_ps
    normal_listener = presence.PresencePubSub()
    normal_listener._redis = normal_redis
    with patch.object(
        presence, "settings", SimpleNamespace(presence_pubsub_channel="presence")
    ):
        await normal_listener._listen_for_updates()
    normal_ps.subscribe.assert_awaited_once_with("presence")
    normal_ps.listen.assert_called_once_with()
    normal_ps.unsubscribe.assert_not_awaited()
    normal_ps.close.assert_not_awaited()
    assert normal_messages_seen == ["subscribe"]

    class FalseyPubSub:
        def __init__(self):
            self.subscribe = AsyncMock()
            self.unsubscribe = AsyncMock()
            self.close = AsyncMock()

        def __bool__(self):
            return False

        def listen(self):
            async def cancelled_messages():
                raise asyncio.CancelledError
                yield  # pragma: no cover

            return cancelled_messages()

    falsey_ps = FalseyPubSub()
    falsey_redis = MagicMock()
    falsey_redis.pubsub.return_value = falsey_ps
    falsey_listener = presence.PresencePubSub()
    falsey_listener._redis = falsey_redis
    with patch.object(
        presence, "settings", SimpleNamespace(presence_pubsub_channel="presence")
    ):
        await falsey_listener._listen_for_updates()
    falsey_ps.subscribe.assert_awaited_once_with("presence")
    falsey_ps.unsubscribe.assert_not_awaited()
    falsey_ps.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_presence_pubsub_start_and_stop_wrappers() -> None:
    from app.api.ws import presence

    with (
        patch.object(presence.presence_pubsub, "initialize", new=AsyncMock()) as init,
        patch.object(presence.presence_pubsub, "shutdown", new=AsyncMock()) as stop,
    ):
        await presence.start_presence_pubsub()
        await presence.stop_presence_pubsub()
    init.assert_awaited_once()
    stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_presence_listener_accepts_synchronous_close_after_subscribe_failure() -> (
    None
):
    from app.api.ws import presence

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock(side_effect=ConnectionError("subscription failed"))
    pubsub.close = MagicMock(return_value=None)
    redis = MagicMock()
    redis.pubsub.return_value = pubsub
    listener = presence.PresencePubSub()
    listener._redis = redis
    handler = AsyncMock()
    with (
        patch.object(
            presence, "settings", SimpleNamespace(presence_pubsub_channel="presence")
        ),
        patch.object(presence, "_handle_presence_pubsub", handler),
        patch.object(presence, "logger") as logger,
    ):
        await listener._listen_for_updates()
    pubsub.subscribe.assert_awaited_once_with("presence")
    pubsub.close.assert_called_once_with()
    pubsub.listen.assert_not_called()
    pubsub.unsubscribe.assert_not_called()
    handler.assert_not_awaited()
    logger.error.assert_called_once()
