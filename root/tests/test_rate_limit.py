import httpx
import pytest
from fastapi import Depends, FastAPI, Response, status
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st
from redis.exceptions import RedisError

from app.auth.security import get_password_hash
from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware
from app.localization import translate
from app.utils import ratelimit as ratelimit_module


@pytest.mark.anyio
async def test_rate_limit_per_ip(root_client):
    for _ in range(5):
        response = await root_client.get("/healthz")
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "5"
    response = await root_client.get("/healthz")
    assert response.status_code == 429
    expected = translate("errors.rate_limit.generic")
    assert response.json()["detail"] == expected
    assert response.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_rate_limit_per_token(root_client):
    headers = {"Authorization": "Bearer token-a"}
    for _ in range(5):
        response = await root_client.get("/healthz", headers=headers)
        assert response.status_code == 200
    blocked = await root_client.get("/healthz", headers=headers)
    assert blocked.status_code == 429

    other = await root_client.get(
        "/healthz", headers={"Authorization": "Bearer token-b"}
    )
    assert other.status_code == 200


@pytest.mark.anyio
async def test_rate_limit_per_cookie(root_client):
    root_client.cookies.set("access_token", "cookie-token-a", path="/")

    for _ in range(5):
        response = await root_client.get("/healthz")
        assert response.status_code == 200

    blocked = await root_client.get("/healthz")
    assert blocked.status_code == 429

    root_client.cookies.set("access_token", "cookie-token-b", path="/")

    other = await root_client.get("/healthz")
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
        identifier="demo",
        namespace="ns",
        limit=1,
        window_seconds=60,
        redis_url="redis://test",
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
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/ping")

    assert response.status_code == status.HTTP_200_OK
    assert "X-RateLimit-Limit" not in response.headers


@hypo_settings(max_examples=25)
@given(
    count=st.integers(min_value=1, max_value=50),
    unit=st.sampled_from(list(rate_limit._TIME_UNITS.keys())),
    separator=st.sampled_from(["/", " per "]),
    leading_ws=st.text(alphabet=" ", min_size=0, max_size=2),
    trailing_ws=st.text(alphabet=" ", min_size=0, max_size=2),
)
def test_parse_rate_limit_accepts_known_units(
    count: int, unit: str, separator: str, leading_ws: str, trailing_ws: str
) -> None:
    fallback = (99, 99)
    value = f"{leading_ws}{count}{separator}{unit}{trailing_ws}"
    parsed = rate_limit.parse_rate_limit(value, fallback=fallback)

    expected_seconds = rate_limit._TIME_UNITS.get(
        unit
    ) or rate_limit._TIME_UNITS.get(  # noqa: SLF001
        unit.rstrip("s")
    )
    assert parsed == (count, expected_seconds)


@hypo_settings(max_examples=25)
@given(
    value=st.text().filter(
        lambda raw: not raw or raw.strip().isdigit() or raw.count("/") > 1
    )
)
def test_parse_rate_limit_invalid_returns_fallback(value: str) -> None:
    fallback = (3, 7)
    assert rate_limit.parse_rate_limit(value, fallback=fallback) == fallback


@hypo_settings(
    max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(identifier=st.text(min_size=1, max_size=12).filter(lambda s: ":" not in s))
@pytest.mark.anyio
async def test_check_rate_limit_blocks_after_limit(
    identifier: str, _rate_limit_redis_client, monkeypatch
):
    monkeypatch.setattr(rate_limit, "_shared_clients", {})
    monkeypatch.setattr(rate_limit, "_shared_client_locks", {})

    namespace = "prop"
    limit = 2
    window = 60

    for _ in range(limit):
        allowed = await rate_limit.check_rate_limit(
            identifier=identifier,
            namespace=namespace,
            limit=limit,
            window_seconds=window,
            redis_url="redis://test",
        )
        assert allowed.allowed

    blocked = await rate_limit.check_rate_limit(
        identifier=identifier,
        namespace=namespace,
        limit=limit,
        window_seconds=window,
        redis_url="redis://test",
    )

    assert blocked.allowed is False
    assert blocked.remaining == 0
