"""Security and lifecycle closure for WebSocket presence handling."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)


@pytest.mark.asyncio
async def test_presence_audience_cache_is_scoped_to_each_user() -> None:
    from app.api.ws import presence

    first_user, second_user = uuid.uuid4(), uuid.uuid4()
    first_audience, second_audience = {uuid.uuid4()}, {uuid.uuid4()}
    audiences = {
        first_user: first_audience,
        second_user: second_audience,
    }
    repository = MagicMock()
    repository.get_presence_audience = AsyncMock(
        side_effect=lambda user_id: audiences[user_id]
    )
    cache = SimpleNamespace(enabled=False)
    original_cache = presence._PRESENCE_DB_CACHE.copy()

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    try:
        presence._PRESENCE_DB_CACHE.clear()
        with (
            patch.object(presence, "get_cache", return_value=cache),
            patch.object(presence, "async_session", fake_session),
            patch.object(presence, "ChatRepository", return_value=repository),
        ):
            assert await presence._get_presence_audience(first_user) == first_audience
            assert await presence._get_presence_audience(second_user) == second_audience
            assert await presence._get_presence_audience(first_user) == first_audience
            assert await presence._get_presence_audience(second_user) == second_audience

        assert repository.get_presence_audience.await_args_list == [
            ((first_user,),),
            ((second_user,),),
        ]
    finally:
        presence._PRESENCE_DB_CACHE.clear()
        presence._PRESENCE_DB_CACHE.update(original_cache)


@pytest.mark.asyncio
async def test_listener_skips_malformed_last_seen_and_cleans_up_on_cancel() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()
    expected_last_seen = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock()
    pubsub_client.unsubscribe = AsyncMock()
    pubsub_client.close = AsyncMock()

    async def messages():
        yield {
            "type": "message",
            "data": json.dumps(
                {
                    "user_id": str(user_id),
                    "active": True,
                    "last_seen": 42,
                    "instance_id": "another-instance",
                }
            ),
        }
        yield {
            "type": "message",
            "data": json.dumps(
                {
                    "user_id": str(user_id),
                    "active": False,
                    "last_seen": expected_last_seen.isoformat(),
                    "instance_id": "another-instance",
                }
            ),
        }
        raise asyncio.CancelledError

    pubsub_client.listen.return_value = messages()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis
    manager = MagicMock()
    manager.is_online.return_value = True
    manager.broadcast_presence = AsyncMock()

    with (
        patch.object(
            presence,
            "settings",
            SimpleNamespace(presence_pubsub_channel="presence:updates"),
        ),
        patch("app.api.ws.connection_manager.manager", manager),
    ):
        await listener._listen_for_updates()

    assert manager.broadcast_presence.await_args_list == [
        (
            (user_id, True, None),
            {
                "source": presence.PRESENCE_SOURCE_PUBSUB,
                "force": True,
                "publish": False,
            },
        ),
        (
            (user_id, False, expected_last_seen),
            {
                "source": presence.PRESENCE_SOURCE_PUBSUB,
                "force": True,
                "publish": False,
            },
        ),
    ]
    pubsub_client.unsubscribe.assert_awaited_once_with("presence:updates")
    pubsub_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_listener_skips_non_object_json_and_continues() -> None:
    from app.api.ws import presence

    user_id = uuid.uuid4()
    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock()
    pubsub_client.unsubscribe = AsyncMock()
    pubsub_client.close = AsyncMock()

    async def messages():
        yield {"type": "message", "data": json.dumps([])}
        yield {
            "type": "message",
            "data": json.dumps(
                {
                    "user_id": str(user_id),
                    "active": True,
                    "instance_id": "another-instance",
                }
            ),
        }
        raise asyncio.CancelledError

    pubsub_client.listen.return_value = messages()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis
    manager = MagicMock()
    manager.is_online.return_value = True
    manager.broadcast_presence = AsyncMock()

    with (
        patch.object(
            presence,
            "settings",
            SimpleNamespace(presence_pubsub_channel="presence:updates"),
        ),
        patch("app.api.ws.connection_manager.manager", manager),
    ):
        await listener._listen_for_updates()

    manager.broadcast_presence.assert_awaited_once_with(
        user_id,
        True,
        None,
        source=presence.PRESENCE_SOURCE_PUBSUB,
        force=True,
        publish=False,
    )
    pubsub_client.unsubscribe.assert_awaited_once_with("presence:updates")
    pubsub_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_listener_closes_pubsub_when_subscribe_fails() -> None:
    from app.api.ws import presence

    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock(side_effect=ConnectionError("offline"))
    pubsub_client.close = AsyncMock()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis

    with patch.object(
        presence,
        "settings",
        SimpleNamespace(presence_pubsub_channel="presence:updates"),
    ):
        await listener._listen_for_updates()

    pubsub_client.subscribe.assert_awaited_once_with("presence:updates")
    pubsub_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_listener_tolerates_falsey_pubsub_during_redis_error() -> None:
    from app.api.ws import presence

    class FalseyPubSub:
        def __bool__(self) -> bool:
            return False

        subscribe = AsyncMock(side_effect=RedisConnectionError("unavailable"))
        close = AsyncMock()

    pubsub_client = FalseyPubSub()
    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis

    with patch.object(
        presence,
        "settings",
        SimpleNamespace(presence_pubsub_channel="presence:updates"),
    ):
        await listener._listen_for_updates()

    pubsub_client.subscribe.assert_awaited_once_with("presence:updates")
    pubsub_client.close.assert_not_awaited()


@pytest.mark.parametrize(
    ("phase", "redis_error"),
    [
        (phase, redis_error)
        for phase in ("subscribe", "listen")
        for redis_error in (RedisConnectionError, RedisTimeoutError)
    ],
)
@pytest.mark.asyncio
async def test_listener_closes_pubsub_on_redis_specific_failures(
    phase: str,
    redis_error: type[Exception],
) -> None:
    from app.api.ws import presence

    pubsub_client = MagicMock()
    pubsub_client.subscribe = AsyncMock()
    pubsub_client.close = AsyncMock()
    if phase == "subscribe":
        pubsub_client.subscribe.side_effect = redis_error("unavailable")
    else:

        async def failing_messages():
            raise redis_error("unavailable")
            yield  # pragma: no cover

        pubsub_client.listen.return_value = failing_messages()

    redis = MagicMock()
    redis.pubsub.return_value = pubsub_client
    listener = presence.PresencePubSub()
    listener._redis = redis

    with patch.object(
        presence,
        "settings",
        SimpleNamespace(presence_pubsub_channel="presence:updates"),
    ):
        await listener._listen_for_updates()

    pubsub_client.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_error", [RedisConnectionError, RedisTimeoutError])
async def test_initialize_falls_back_for_redis_specific_errors(
    redis_error: type[Exception],
) -> None:
    from app.api.ws import presence

    fallback_redis = MagicMock()
    listener_task = MagicMock()

    def create_task_without_running(coroutine):
        coroutine.close()
        return listener_task

    settings = SimpleNamespace(
        presence_pubsub_enabled=True,
        cache_redis_url="redis://presence",
        presence_pubsub_channel="presence:updates",
        redis_pool_size=3,
    )
    with (
        patch.object(presence, "settings", settings),
        patch(
            "app.deps.cache.get_cache_client",
            new=AsyncMock(side_effect=redis_error("unavailable")),
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
        pubsub = presence.PresencePubSub()
        await pubsub.initialize()

    assert pubsub._redis is fallback_redis
    assert pubsub._pubsub_task is listener_task
    from_url.assert_called_once_with(
        "redis://presence", decode_responses=True, max_connections=3
    )
