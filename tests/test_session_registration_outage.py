"""Cache registration must not strand a durably committed login session."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import AuthenticationError, AuthorizationError, ResponseError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import func, select

from app.api.deps import auth as auth_deps
from app.auth.redis_session import RedisSessionBackend
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.database import async_session
from app.models import ActiveSession
from app.services import session_service
from app.services.auth import redis_session as session_cache
from tests.fixtures.infrastructure.infrastructure import _configure_csrf_client
from tests.helpers.synthetic_credentials import make_test_password


@pytest.mark.parametrize(
    "error_type",
    [
        RedisConnectionError,
        RedisTimeoutError,
        AuthenticationError,
        AuthorizationError,
        ConnectionError,
        TimeoutError,
        OSError,
    ],
)
async def test_registration_tolerates_cache_connection_and_timeout_failures(
    monkeypatch, error_type
):
    cache = AsyncMock()
    cache.set.side_effect = error_type("synthetic cache transport outage")
    backend = RedisSessionBackend(cache)
    monkeypatch.setattr(
        session_service, "get_session_backend", AsyncMock(return_value=backend)
    )

    await session_service.register_session_bg(
        uuid4(), "cache-outage", datetime.now(UTC) + timedelta(minutes=5), None, None
    )

    cache.set.assert_awaited_once()


@pytest.mark.parametrize("failure_stage", ["factory", "registration"])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, ResponseError])
async def test_registration_preserves_configuration_and_unexpected_errors(
    monkeypatch, failure_stage, error_type
):
    failure = error_type("synthetic non-transport failure")
    backend = AsyncMock()
    factory = AsyncMock(return_value=backend)
    if failure_stage == "factory":
        factory.side_effect = failure
    else:
        backend.register_session.side_effect = failure
    monkeypatch.setattr(session_service, "get_session_backend", factory)

    with pytest.raises(error_type) as caught:
        await session_service.register_session_bg(
            uuid4(), "invalid-backend", datetime.now(UTC), None, None
        )

    assert caught.value is failure


async def _persisted_active_count(user_id):
    # A separate transaction verifies the durable outcome after HTTP cleanup.
    async with async_session() as observer:
        return await observer.scalar(
            select(func.count())
            .select_from(ActiveSession)
            .where(
                ActiveSession.user_id == user_id,
                ActiveSession.revoked_at.is_(None),
                ActiveSession.expires_at > datetime.now(UTC),
            )
        )


@pytest.mark.parametrize("error_type", [RedisConnectionError, RedisTimeoutError])
async def test_http_login_survives_cache_outage_without_bypassing_revocation(
    app, user_factory, monkeypatch, mock_cache_backend, error_type
):
    password = make_test_password()
    user = await user_factory(hashed_password=await get_password_hash(password))
    user_id, email = user.id, user.email
    # Keep the optional session cache distinct from the mandatory revocation store.
    cache = FakeRedis(decode_responses=True)
    monkeypatch.setattr(mock_cache_backend, "_client", cache)
    monkeypatch.setattr(settings, "session_storage_backend", "redis")
    monkeypatch.setattr(settings, "cache_redis_url", "redis://cache.invalid/0")
    monkeypatch.setattr(
        session_cache, "_get_shared_client", AsyncMock(return_value=cache)
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver/api/v1",
    )
    try:
        async with client:
            await _configure_csrf_client(client, "/auth/csrf-cookie")
            with monkeypatch.context() as outage:
                failed_set = AsyncMock(side_effect=error_type("synthetic cache outage"))
                outage.setattr(cache, "set", failed_set)
                outage.setattr(
                    cache,
                    "hset",
                    AsyncMock(side_effect=error_type("synthetic cache outage")),
                )
                outage.setattr(
                    cache,
                    "hgetall",
                    AsyncMock(side_effect=error_type("synthetic cache outage")),
                )
                response = await client.post(
                    "/auth/login", data={"username": email, "password": password}
                )
                assert response.status_code == 200
                assert client.cookies.get("access_token_v2")
                failed_set.assert_awaited_once()
                assert await _persisted_active_count(user_id) == 1
                # Real auth falls back to the committed database session.
                profile = await client.get("/users/me")
                assert profile.status_code == 200
                assert profile.json()["id"] == str(user_id)
                # Cache tolerance must not turn a security-store failure into access.
                with monkeypatch.context() as security_outage:
                    security_outage.setattr(
                        auth_deps,
                        "get_revocation_redis_client",
                        AsyncMock(
                            side_effect=error_type("synthetic revocation outage")
                        ),
                    )
                    rejected = await client.get("/users/me")
                    assert rejected.status_code == 503
                    assert rejected.json()["code"] == "session_verification_unavailable"

            # Recovery can create the second legitimate session; no hidden retry
            # sessions consumed capacity. The ordinary limit remains enforced.
            response = await client.post(
                "/auth/login", data={"username": email, "password": password}
            )
            assert response.status_code == 200
            assert await _persisted_active_count(user_id) == 2
            response = await client.post(
                "/auth/login", data={"username": email, "password": password}
            )
            assert response.status_code == 403
            assert response.json()["detail"] == "too_many_sessions"
            assert await _persisted_active_count(user_id) == 2
    finally:
        await cache.aclose()
