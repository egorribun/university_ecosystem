import httpx
import pytest
from fastapi import Depends, FastAPI, status

from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware
from app.localization import translate
from app.utils import ratelimit as ratelimit_module


@pytest.mark.anyio
async def test_rate_limit_per_ip(async_client):
    for _ in range(5):
        response = await async_client.get("/healthz")
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "5"
    response = await async_client.get("/healthz")
    assert response.status_code == 429
    expected = translate("errors.rate_limit.generic")
    assert response.json()["detail"] == expected
    assert response.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_rate_limit_per_token(async_client):
    headers = {"Authorization": "Bearer token-a"}
    for _ in range(5):
        response = await async_client.get("/healthz", headers=headers)
        assert response.status_code == 200
    blocked = await async_client.get("/healthz", headers=headers)
    assert blocked.status_code == 429

    other = await async_client.get(
        "/healthz", headers={"Authorization": "Bearer token-b"}
    )
    assert other.status_code == 200


@pytest.mark.anyio
async def test_sensitive_login_rate_limit(async_client, user_factory):
    password = "ValidPass123!"
    user = await user_factory(
        email="login-rate@example.com",
        hashed_password=get_password_hash(password),
    )
    data = {"username": user.email, "password": "wrong-password"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    for _ in range(4):
        response = await async_client.post("/auth/login", data=data, headers=headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    blocked = await async_client.post("/auth/login", data=data, headers=headers)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.anyio
async def test_sensitive_forgot_password_rate_limit(async_client, user_factory):
    user = await user_factory(email="forgot-rate@example.com")
    payload = {"email": user.email}

    for _ in range(4):
        response = await async_client.post("/password/forgot", json=payload)
        assert response.status_code == status.HTTP_200_OK

    blocked = await async_client.post("/password/forgot", json=payload)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.anyio
async def test_rate_limit_memory_backend_blocks_requests():
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        redis_url="memory://",
        limit=2,
        window_seconds=60,
    )

    @app.get("/ping")
    async def _ping():  # pragma: no cover - minimal endpoint definition
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first = await client.get("/ping")
        second = await client.get("/ping")
        third = await client.get("/ping")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_sensitive_dependency_memory_backend():
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    settings.rate_limit_storage_backend = "memory"
    settings.rate_limit_storage_uri = "memory://"
    ratelimit_module.limiter.reset()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-dep"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():  # pragma: no cover - minimal endpoint
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            first = await client.get("/limited")
            second = await client.get("/limited")
            third = await client.get("/limited")
    finally:
        settings.rate_limit_storage_backend = original_backend
        settings.rate_limit_storage_uri = original_uri

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.anyio
async def test_sensitive_dependency_redis_backend(
    monkeypatch, _rate_limit_redis_client
):
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    settings.rate_limit_storage_backend = "redis"
    settings.rate_limit_storage_uri = "redis://test"

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="redis-dep"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():  # pragma: no cover - minimal endpoint
        return {"ok": True}

    def _fail_check(*args, **kwargs):
        raise AssertionError(
            "Memory limiter should not run when Redis backend is configured"
        )

    monkeypatch.setattr(ratelimit_module.limiter, "check", _fail_check)

    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            first = await client.get("/limited")
            second = await client.get("/limited")
            third = await client.get("/limited")
    finally:
        settings.rate_limit_storage_backend = original_backend
        settings.rate_limit_storage_uri = original_uri

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.headers.get("Retry-After") is not None
