import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        (b"mfa_epoch", b"not-an-integer"),
        (b"mfa_epoch", b""),
        (b"mfa_epoch", b"1.5"),
        (b"mfa_epoch", b"\xff"),
        (b"fingerprint_hash", b"\xff"),
        (b"\xff", b"unknown-field"),
    ],
)
async def test_redis_session_malformed_hash_is_a_read_only_miss(
    monkeypatch, field, value, caplog
):
    async with FakeRedis(decode_responses=False) as client:
        service = RedisSessionService(redis_url="redis://localhost")
        monkeypatch.setattr(
            "app.services.auth.redis_session._get_shared_client",
            AsyncMock(return_value=client),
        )
        key = "session:v2:malformed-test"
        data = {
            b"user_id": str(uuid4()).encode(),
            b"is_active": b"1",
            b"mfa_epoch": b"3",
        }
        data[field] = value
        await client.hset(key, mapping=data)
        assert await service.get_session("malformed-test") is None
        assert await client.hgetall(key) == data
        assert not caplog.records


@pytest.mark.asyncio
@pytest.mark.parametrize("epoch", [None, b"0", b"17"])
async def test_redis_session_valid_epoch_and_legacy_default(monkeypatch, epoch):
    async with FakeRedis(decode_responses=False) as client:
        service = RedisSessionService(redis_url="redis://localhost")
        monkeypatch.setattr(
            "app.services.auth.redis_session._get_shared_client",
            AsyncMock(return_value=client),
        )
        data = {b"user_id": str(uuid4()).encode(), b"is_active": b"1"}
        if epoch is not None:
            data[b"mfa_epoch"] = epoch
        await client.hset("session:v2:valid-test", mapping=data)
        result = await service.get_session("valid-test")
        assert result is not None
        assert result["user_id"] == data[b"user_id"].decode()
        assert result["mfa_epoch"] == (int(epoch) if epoch is not None else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), ValueError("transport")])
async def test_redis_session_transport_errors_are_not_parse_misses(monkeypatch, error):
    client = AsyncMock()
    client.hgetall.side_effect = error
    monkeypatch.setattr(
        "app.services.auth.redis_session._get_shared_client",
        AsyncMock(return_value=client),
    )
    service = RedisSessionService(redis_url="redis://localhost")
    with pytest.raises(type(error)) as caught:
        await service.get_session("transport-test")
    assert caught.value is error
