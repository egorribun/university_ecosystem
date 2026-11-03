"""AUD-164: verified identities separate traffic, never auth attack budgets."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.auth.security import _mint_pure_jwt
from app.core.config import settings
from app.core.ratelimit import RateLimitMiddleware, clear_memory_state
from app.core.ratelimit.fastapi import sensitive_route_limit


@pytest.fixture(autouse=True)
def isolated_buckets(monkeypatch):
    clear_memory_state()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "trusted_proxies_list", [])
    yield
    clear_memory_state()


def _app(path, *, sensitive):
    app = FastAPI()
    dependencies = (
        [Depends(sensitive_route_limit(limit=2, window_sec=60))] if sensitive else []
    )
    if not sensitive:
        app.add_middleware(
            RateLimitMiddleware, storage_backend="memory", limit=2, window_seconds=60
        )

    @app.post(path, dependencies=dependencies)
    async def limited():
        return {"ok": True}

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize("credential", ["bearer", "cookie"])
async def test_verified_users_have_independent_budgets(sensitive, credential):
    path = "/api/v1/news"
    subject = uuid4()
    first = _mint_pure_jwt(subject)
    rotated = _mint_pure_jwt(subject)
    second = _mint_pure_jwt(uuid4())
    app = _app(path, sensitive=sensitive)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = []
        for value in (first, first, rotated, second, second, second):
            headers = (
                {"Authorization": f"Bearer {value}"}
                if credential == "bearer"
                else {"Cookie": f"access_token_v2={value}"}
            )
            response = await client.post(path, headers=headers)
            statuses.append(response.status_code)
    assert statuses == [200, 200, 429, 200, 200, 429]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/login",
        "/api/v1/auth/login/json",
        "/api/v1/auth/register",
        "/api/v1/password/forgot",
        "/api/v1/password/reset",
    ],
)
async def test_auth_budget_stays_on_ip_when_valid_users_rotate(sensitive, path):
    app = _app(path, sensitive=sensitive)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = []
        for _ in range(3):
            value = _mint_pure_jwt(uuid4())
            response = await client.post(
                path, headers={"Authorization": f"Bearer {value}"}
            )
            statuses.append(response.status_code)
    assert statuses == [200, 200, 429]
    other_transport = httpx.ASGITransport(app=app, client=("203.0.113.8", 5000))
    async with httpx.AsyncClient(
        transport=other_transport, base_url="http://test"
    ) as client:
        assert (await client.post(path)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_invalid_expired_and_anonymous_share_ip_budget(sensitive):
    path = "/api/v1/news"
    app = _app(path, sensitive=sensitive)
    expired = _mint_pure_jwt(
        uuid4(), extra_claims={"exp": datetime.now(UTC) - timedelta(days=1)}
    )
    valid = _mint_pure_jwt(uuid4())
    prefix, _signature = valid.rsplit(".", 1)
    forged = f"{prefix}.invalid-signature"
    transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = []
        for headers in (
            {},
            {"Authorization": f"Bearer {expired}"},
            {"Authorization": f"Bearer {forged}"},
        ):
            statuses.append((await client.post(path, headers=headers)).status_code)
        assert statuses == [200, 200, 429]
        assert (
            await client.post(path, headers={"Authorization": f"Bearer {valid}"})
        ).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_untrusted_forwarded_values_cannot_rotate_ip_budget(sensitive):
    path = "/api/v1/auth/login"
    app = _app(path, sensitive=sensitive)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = []
        for host in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
            headers = {"X-Forwarded-For": host, "Forwarded": f"for={host}"}
            statuses.append((await client.post(path, headers=headers)).status_code)
    assert statuses == [200, 200, 429]
