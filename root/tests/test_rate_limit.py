import httpx
import pytest
from fastapi import FastAPI, status

from app.auth.security import get_password_hash
from app.core.rate_limit import RateLimitMiddleware
from app.localization import translate


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
