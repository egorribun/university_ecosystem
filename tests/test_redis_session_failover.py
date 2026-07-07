from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.services.auth.redis_session import RedisSessionService


@pytest.mark.asyncio
async def test_redis_session_backend_empty_url() -> None:
    # 1. Initialize backend and force empty URL
    backend = RedisSessionService()
    backend.redis_url = None
    jti = "jti-123"
    user_id = uuid.uuid4()

    # 2. Assert all methods return early without throwing errors
    await backend.create_session(jti, user_id, None, None)
    assert await backend.get_session(jti) is None
    await backend.update_last_seen(jti)
    await backend.revoke_session(jti)


@pytest.mark.asyncio
async def test_redis_session_backend_create_session_fails() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"
    user_id = uuid.uuid4()

    mock_client = AsyncMock()
    mock_client.hset.side_effect = RedisError("redis connection failed")

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=mock_client,
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        await backend.create_session(jti, user_id, None, None)
        # Should catch exception and log a warning
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_redis_session_backend_get_session_fails() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = RedisError("redis connection failed")

    with patch(
        "app.services.auth.redis_session._get_shared_client", return_value=mock_client
    ):
        # Should catch exception and return None (fail open)
        data = await backend.get_session(jti)
        assert data is None


@pytest.mark.asyncio
async def test_redis_session_backend_update_last_seen_fails() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    mock_client = AsyncMock()
    mock_client.hset.side_effect = RedisError("redis connection failed")

    with patch(
        "app.services.auth.redis_session._get_shared_client", return_value=mock_client
    ):
        # Should catch exception silently
        await backend.update_last_seen(jti)


@pytest.mark.asyncio
async def test_redis_session_backend_revoke_session_nested_failures() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    mock_client = AsyncMock()
    mock_client.hset.return_value = 1
    # 1. Trigger RedisError on client.ttl (line 172)
    mock_client.ttl.side_effect = RedisError("ttl check failed")
    # 2. Trigger RedisError on client.delete (line 177)
    mock_client.delete.side_effect = RedisError("delete key failed")

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=mock_client,
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        await backend.revoke_session(jti)
        # Verify warnings are logged for both nested failures
        assert mock_logger.warning.call_count == 2


@pytest.mark.asyncio
async def test_redis_session_backend_revoke_session_main_failure() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    mock_client = AsyncMock()
    # Trigger main RedisError on client.hset (line 179)
    mock_client.hset.side_effect = RedisError("redis connection failed")

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=mock_client,
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        with pytest.raises(RedisError, match="redis connection failed"):
            await backend.revoke_session(jti)
        mock_logger.error.assert_called_once()
