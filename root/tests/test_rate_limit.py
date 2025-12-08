import httpx
import pytest
from fastapi import Depends, FastAPI, Response, status

from app.auth.security import get_password_hash
from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware
from app.localization import translate
from app.utils import ratelimit as ratelimit_module
from redis.exceptions import RedisError


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
async def test_rate_limit_per_cookie(async_client):
    async_client.cookies.set("access_token", "cookie-token-a", path="/")

    for _ in range(5):
        response = await async_client.get("/healthz")
        assert response.status_code == 200

    blocked = await async_client.get("/healthz")
    assert blocked.status_code == 429

    async_client.cookies.set("access_token", "cookie-token-b", path="/")

    other = await async_client.get("/healthz")
    assert other.status_code == 200


@pytest.mark.anyio
async def test_rate_limit_skips_static_paths():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        redis_url="memory://",
        limit=2,
        window_seconds=60,
    )

    @app.get("/static/example.png")
    async def _static() -> Response:  # pragma: no cover - simple passthrough
        return Response(content=b"", media_type="image/png")

    @app.get("/media/example.png")
    async def _media() -> Response:  # pragma: no cover - simple passthrough
        return Response(content=b"", media_type="image/png")

    @app.get("/storage/example.png")
    async def _storage() -> Response:  # pragma: no cover - simple passthrough
        return Response(content=b"", media_type="image/png")

    @app.get("/assets/app.js")
    async def _assets() -> Response:  # pragma: no cover - simple passthrough
        return Response(content=b"console.log('hi');", media_type="text/javascript")

    @app.get("/limited")
    async def _limited():  # pragma: no cover - simple passthrough
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        for path in [
            "/static/example.png",
            "/media/example.png",
            "/storage/example.png",
            "/assets/app.js",
        ]:
            for _ in range(3):
                static_response = await client.get(path)
                assert static_response.status_code == status.HTTP_200_OK

        head_response = await client.head("/media/example.png")
        assert head_response.status_code == status.HTTP_200_OK

        first = await client.get("/limited")
        second = await client.get("/limited")
        third = await client.get("/limited")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


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
async def test_sensitive_dependency_memory_backend_resolves_proxy_headers():
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    settings.rate_limit_storage_backend = "memory"
    settings.rate_limit_storage_uri = "memory://"
    ratelimit_module.limiter.reset()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-proxy"
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
            first = await client.get(
                "/limited",
                headers={"X-Forwarded-For": " 2001:DB8::1 "},
            )
            second = await client.get(
                "/limited",
                headers={"X-Forwarded-For": "2001:db8::1"},
            )
            third = await client.get(
                "/limited",
                headers={"X-Forwarded-For": "2001:db8::1"},
            )
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


@pytest.mark.anyio
async def test_sensitive_dependency_redis_backend_forwarded_header(
    monkeypatch, _rate_limit_redis_client
):
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    settings.rate_limit_storage_backend = "redis"
    settings.rate_limit_storage_uri = "redis://test"

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="redis-proxy"
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
            first = await client.get(
                "/limited",
                headers={
                    "Forwarded": 'for="[203.0.113.42]:1234";proto=https;by=proxy',
                },
            )
            second = await client.get(
                "/limited",
                headers={
                    "Forwarded": 'for="[203.0.113.42]:1234";proto=https;by=proxy',
                },
            )
            third = await client.get(
                "/limited",
                headers={
                    "Forwarded": 'for="[203.0.113.42]:1234";proto=https;by=proxy',
                },
            )
    finally:
        settings.rate_limit_storage_backend = original_backend
        settings.rate_limit_storage_uri = original_uri

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_enforce_rate_limit_falls_back_on_redis_error(monkeypatch):
    monkeypatch.setattr(rate_limit, "_memory_buckets", {})

    async def failing_redis(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RedisError("unknown command EVAL")

    monkeypatch.setattr(rate_limit, "_redis_rate_limit", failing_redis)

    await rate_limit.enforce_rate_limit(
        identifier="demo", namespace="ns", limit=1, window_seconds=60, redis_url="redis://test"
    )

    with pytest.raises(rate_limit.RateLimitExceeded):
        await rate_limit.enforce_rate_limit(
            identifier="demo",
            namespace="ns",
            limit=1,
            window_seconds=60,
            redis_url="redis://test",
        )


@pytest.mark.anyio
async def test_rate_limit_middleware_allows_when_redis_fails(monkeypatch):
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="redis",
        redis_url="redis://test",  # not actually used
        limit=1,
        window_seconds=60,
    )

    @app.get("/ping")
    async def _ping():  # pragma: no cover - simple response
        return {"ok": True}

    async def fail_check(self, identifier):  # type: ignore[no-untyped-def]
        raise RedisError("boom")

    monkeypatch.setattr(RateLimitMiddleware, "_check_limit", fail_check)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ping")

    assert response.status_code == status.HTTP_200_OK
    assert "X-RateLimit-Limit" not in response.headers
