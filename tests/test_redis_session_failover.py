from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
async def test_redis_session_revoke_writes_durable_tombstone_before_cache_delete() -> (
    None
):
    """The service writes security state to its dedicated Redis first."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-to-revoke"

    cache_client = AsyncMock()
    revocation_client = AsyncMock()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=cache_client,
        ),
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            return_value=revocation_client,
        ),
    ):
        await backend.revoke_session(jti, expires_at=expires_at)

    written_ttl = revocation_client.set.await_args.kwargs["ex"]
    assert 295 <= written_ttl <= 300
    revocation_client.set.assert_awaited_once_with(
        f"revoked:jti:{jti}", "1", ex=written_ttl
    )
    cache_client.delete.assert_awaited_once_with(f"session:v2:{jti}")
    cache_client.eval.assert_not_awaited()
    revocation_client.publish.assert_awaited_once_with("session:revocations", jti)


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_ttl", [0, -1, -2])
async def test_redis_session_revoke_uses_expiry_when_cached_key_has_no_ttl(
    redis_ttl: int,
) -> None:
    """Revocation stays effective after expiry loss or cache eviction."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-expired"

    cache_client = AsyncMock()
    cache_client.ttl.return_value = redis_ttl
    revocation_client = AsyncMock()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=cache_client,
        ),
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            return_value=revocation_client,
        ),
    ):
        await backend.revoke_session(jti, expires_at=expires_at)

    written_ttl = revocation_client.set.await_args.kwargs["ex"]
    assert 295 <= written_ttl <= 300
    revocation_client.set.assert_awaited_once_with(
        f"revoked:jti:{jti}", "1", ex=written_ttl
    )
    cache_client.delete.assert_awaited_once_with(f"session:v2:{jti}")
    cache_client.ttl.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_session_backend_empty_url() -> None:
    # 1. Initialize backend and force empty URL
    backend = RedisSessionService()
    backend.redis_url = None
    jti = "jti-123"
    user_id = uuid.uuid4()

    # 2. Assert all methods return early without throwing errors
    revocation_client = AsyncMock()
    with patch(
        "app.services.auth.redis_session.get_revocation_redis_client",
        return_value=revocation_client,
    ):
        await backend.create_session(jti, user_id, None, None)
        assert await backend.get_session(jti) is None
        await backend.update_last_seen(jti)
        await backend.revoke_session(jti)

    revocation_client.set.assert_awaited_once()
    revocation_client.publish.assert_awaited_once_with("session:revocations", jti)


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
async def test_redis_session_backend_publish_failure_keeps_revocation_successful() -> (
    None
):
    """A durable tombstone remains authoritative when Pub/Sub is unavailable."""
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-publish-offline"

    cache_client = AsyncMock()
    revocation_client = AsyncMock()
    revocation_client.publish.side_effect = RedisError("pubsub unavailable")

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=cache_client,
        ),
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            return_value=revocation_client,
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        await backend.revoke_session(jti)

    revocation_client.set.assert_awaited_once()
    cache_client.delete.assert_awaited_once_with(f"session:v2:{jti}")
    mock_logger.warning.assert_called_once_with(
        "Failed to publish session revocation for jti=%s",
        jti,
    )


@pytest.mark.asyncio
async def test_redis_session_backend_revoke_tombstone_failure_is_propagated() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    cache_client = AsyncMock()
    revocation_client = AsyncMock()
    revocation_client.set.side_effect = RedisError("tombstone write failed")

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=cache_client,
        ),
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            return_value=revocation_client,
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        with pytest.raises(RedisError, match="tombstone write failed"):
            await backend.revoke_session(jti)
        cache_client.delete.assert_not_awaited()
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_redis_session_backend_revoke_session_main_failure() -> None:
    backend = RedisSessionService(redis_url="redis://localhost:6379/0")
    jti = "jti-123"

    cache_client = AsyncMock()

    with (
        patch(
            "app.services.auth.redis_session._get_shared_client",
            return_value=cache_client,
        ),
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            side_effect=RedisError("redis connection failed"),
        ),
        patch("app.services.auth.redis_session.logger") as mock_logger,
    ):
        with pytest.raises(RedisError, match="redis connection failed"):
            await backend.revoke_session(jti)
        mock_logger.error.assert_called_once()
