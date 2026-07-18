from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.services.auth.redis_session import RedisSessionService


@pytest.mark.asyncio
async def test_redis_session_get_inactive_returns_none() -> None:
    """Line 111: get_session returns None when is_active != '1'."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-inactive"

    # Simulate a hash that exists but is_active = "0"
    mock_client = AsyncMock()
    mock_client.hgetall.return_value = {
        b"user_id": b"some-user-id",
        b"session_id": b"",
        b"fingerprint_hash": b"",
        b"mfa_verified_at": b"",
        b"last_seen_at": b"2026-01-01T00:00:00+00:00",
        b"created_at": b"2026-01-01T00:00:00+00:00",
        b"is_active": b"0",  # <-- explicitly inactive
    }

    with patch(
        "app.services.auth.redis_session._get_shared_client",
        return_value=mock_client,
    ):
        result = await backend.get_session(jti)

    assert result is None, "Inactive session should return None"


@pytest.mark.asyncio
async def test_redis_session_revoke_writes_blocklist_when_ttl_positive() -> None:
    """Lines 166-175: revoke_session writes revoked:jti:<jti> when TTL > 0."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-to-revoke"

    mock_client = AsyncMock()
    mock_client.hset.return_value = 1
    mock_client.ttl.return_value = 300  # positive TTL → blocklist path executed
    mock_client.set.return_value = True
    mock_client.delete.return_value = 1

    with patch(
        "app.services.auth.redis_session._get_shared_client",
        return_value=mock_client,
    ):
        await backend.revoke_session(jti)

    # Verify the blocklist key was written with the correct name and TTL
    mock_client.set.assert_awaited_once_with(f"revoked:jti:{jti}", "1", ex=300)


@pytest.mark.asyncio
async def test_redis_session_revoke_no_blocklist_when_ttl_zero() -> None:
    """Lines 166-175 FALSE path: when TTL <= 0, blocklist key is NOT written."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-expired"

    mock_client = AsyncMock()
    mock_client.hset.return_value = 1
    mock_client.ttl.return_value = 0  # already expired → skip blocklist write
    mock_client.delete.return_value = 1

    with patch(
        "app.services.auth.redis_session._get_shared_client",
        return_value=mock_client,
    ):
        await backend.revoke_session(jti)

    # Verify the blocklist set() was NOT called (TTL was 0)
    mock_client.set.assert_not_awaited()


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
