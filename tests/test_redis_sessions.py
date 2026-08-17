from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis

from app.auth.fingerprint import SessionFingerprint
from app.core.config import settings
from app.services.auth.redis_session import RedisSessionService


def test_redis_session_service_defaults_to_shared_cache_redis(monkeypatch) -> None:
    """Revocation writers must use the Redis namespace read by ws-hub."""
    monkeypatch.setattr(settings, "cache_redis_url", "redis://cache.internal:6379/0")
    monkeypatch.setattr(
        settings,
        "rate_limit_storage_uri",
        "redis://rate-limit.internal:6379/1",
    )

    service = RedisSessionService()

    assert service.redis_url == "redis://cache.internal:6379/0"


@pytest.mark.asyncio
async def test_redis_session_lifecycle_v2(monkeypatch, request):
    # 1. Mock parameters
    monkeypatch.setattr(settings, "access_token_expire_minutes", 30)
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://localhost")

    # 2. Mock Redis client
    fake_client = FakeRedis(decode_responses=True)

    async def mock_get_client(url):
        return fake_client

    from unittest.mock import patch

    patcher = patch(
        "app.services.auth.redis_session._get_shared_client",
        side_effect=mock_get_client,
    )
    patcher.start()
    request.addfinalizer(patcher.stop)

    # 3. Initialize Service
    service = RedisSessionService(redis_url="redis://localhost")

    user_id = uuid4()
    jti = "test-jti-v2"
    fingerprint = SessionFingerprint(
        user_agent="test-agent",
        ip_address="127.0.0.1",
        accept_language="en",
        fingerprint_hash="hash123",
    )
    now = datetime.now(UTC)

    # 4. Create
    await service.create_session(jti, user_id, fingerprint, now)

    # Check raw redis
    raw_exists = await fake_client.exists(f"session:v2:{jti}")
    assert raw_exists

    # 5. Get
    session = await service.get_session(jti)
    assert session is not None
    assert session["user_id"] == str(user_id)

    # 6. Update Activity
    await service.update_last_seen(jti)
    raw_exists_2 = await fake_client.exists(f"session:v2:{jti}")
    assert raw_exists_2

    # 7. Revoke
    await service.revoke_session(jti)
    session_gone = await service.get_session(jti)
    assert session_gone is None
    raw_exists_3 = await fake_client.exists(f"session:v2:{jti}")
    assert not raw_exists_3
