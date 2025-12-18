from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis

from app.auth.redis_session import RedisSessionBackend


@pytest.mark.anyio
async def test_redis_session_lifecycle():
    redis_client = FakeRedis(encoding="utf-8", decode_responses=True)
    backend = RedisSessionBackend(redis_client)

    user_id = 1
    jti = "test-jti"
    expires_at = datetime.now(UTC) + timedelta(minutes=30)

    # Register session
    await backend.register_session(user_id, jti, expires_at, {"ip": "127.0.0.1"})

    # Check validity
    assert await backend.is_session_valid(jti) is True
    assert await backend.is_session_valid("wrong-jti") is False

    # Revoke session
    await backend.revoke_session(jti)
    assert await backend.is_session_valid(jti) is False


@pytest.mark.anyio
async def test_redis_session_expiration():
    redis_client = FakeRedis(encoding="utf-8", decode_responses=True)
    backend = RedisSessionBackend(redis_client)

    user_id = 1
    jti = "expiring-jti"
    # Set expiration in the past (already expired)
    expires_at = datetime.now(UTC) - timedelta(minutes=1)

    await backend.register_session(user_id, jti, expires_at)

    # Should not be valid
    assert await backend.is_session_valid(jti) is False
