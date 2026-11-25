"""Redis session failures retain diagnostics without logging session data."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.auth import redis_session as session_backend
from app.services import session_service
from app.services.auth import redis_session as session_cache


@pytest.mark.asyncio
async def test_registration_warning_omits_session_data(monkeypatch):
    user_id, jti = uuid4(), str(uuid4())
    fault = RedisConnectionError(f"cache failed for {user_id} / {jti}")
    factory = AsyncMock(side_effect=fault)
    logger = Mock()
    monkeypatch.setattr(session_service, "get_session_backend", factory)
    monkeypatch.setattr(session_service, "logger", logger)

    await session_service.register_session_bg(
        user_id, jti, datetime.now(UTC), None, None
    )

    logger.warning.assert_called_once_with(
        "Failed to cache session in Redis",
        extra={
            "component": "session_backend",
            "operation": "register",
            "error_type": "ConnectionError",
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "level", "message"),
    [
        ("create", "warning", "Failed to cache session metadata in Redis"),
        ("invalidate", "warning", "Failed to invalidate cached session metadata"),
        ("publish", "warning", "Failed to publish session revocation"),
        ("revoke", "error", "Failed to revoke session in Redis"),
    ],
)
async def test_metadata_failure_logs_only_error_type(
    monkeypatch, operation, level, message
):
    jti = str(uuid4())
    fault = RedisConnectionError(f"cache failed for {jti}")
    cache, revocation = AsyncMock(), AsyncMock()
    tombstone = AsyncMock()
    logger = Mock()
    monkeypatch.setattr(
        session_cache, "_get_shared_client", AsyncMock(return_value=cache)
    )
    monkeypatch.setattr(
        session_cache, "get_revocation_redis_client", AsyncMock(return_value=revocation)
    )
    monkeypatch.setattr(session_cache, "revoke_with_tombstone", tombstone)
    monkeypatch.setattr(session_cache, "logger", logger)
    service = session_cache.RedisSessionService(redis_url="redis://cache.invalid")

    if operation == "create":
        cache.hset.side_effect = fault
        await service.create_session(jti, uuid4(), None, None)
    elif operation == "invalidate":
        cache.delete.side_effect = fault
        await service.invalidate_session_cache(jti)
    elif operation == "publish":
        revocation.publish.side_effect = fault
        await service.revoke_session(jti)
        tombstone.assert_awaited_once()
    else:
        tombstone.side_effect = fault
        with pytest.raises(RedisConnectionError) as raised:
            await service.revoke_session(jti)
        assert raised.value is fault
        revocation.publish.assert_not_awaited()

    getattr(logger, level).assert_called_once_with(
        message, error_type="ConnectionError"
    )


@pytest.mark.asyncio
async def test_backend_revocation_warning_omits_session_data(monkeypatch):
    jti = str(uuid4())
    client = AsyncMock()
    client.publish.side_effect = RedisConnectionError(f"pubsub failed for {jti}")
    tombstone = AsyncMock()
    logger = Mock()
    monkeypatch.setattr(session_backend, "revoke_with_tombstone", tombstone)
    monkeypatch.setattr(session_backend, "logger", logger)

    await session_backend.RedisSessionBackend(client).revoke_session(jti)

    tombstone.assert_awaited_once()
    logger.warning.assert_called_once_with(
        "Failed to publish session revocation", error_type="ConnectionError"
    )
