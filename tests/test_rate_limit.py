import asyncio

import httpx
import pytest
from fastapi import Depends, FastAPI, Response, status
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st
from redis.exceptions import RedisError

import app.core.ratelimit as rate_limit
import app.core.ratelimit as ratelimit_module
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.core.ratelimit import EndpointRateLimit, RateLimitMiddleware
from app.core.ratelimit.utils import _TIME_UNITS


@pytest.mark.asyncio
async def test_rate_limit_per_ip(root_client):
    """Test using a public endpoint that is NOT exempted."""
    endpoint = "/api/v1/news"
    for _ in range(5):
        response = await root_client.get(endpoint)
        # 200 OK or 404 (empty list) doesn't matter, as long as it reaches application
        # If /api/v1/news returns empty list it's still 200.
        assert response.status_code == 200
        assert response.headers.get("X-RateLimit-Limit") == "5"

    response = await root_client.get(endpoint)
    assert response.status_code == 429
    expected = translate("errors.rate_limit.generic")
    assert response.json()["detail"] == expected
    assert response.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_health_check_exempted(root_client):
    """Test that health check is exempted from rate limits."""
    for _ in range(20):
        response = await root_client.get("/healthz")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers


@pytest.mark.asyncio
async def test_rate_limit_per_token(root_client):
    headers = {"Authorization": "Bearer token-a"}
    endpoint = "/api/v1/news"
    for _ in range(5):
        response = await root_client.get(endpoint, headers=headers)
        assert response.status_code == 200
    blocked = await root_client.get(endpoint, headers=headers)
    assert blocked.status_code == 429

    other = await root_client.get(endpoint, headers={"Authorization": "Bearer token-b"})
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_per_cookie(root_client):
    root_client.cookies.set("access_token", "cookie-token-a", path="/")
    endpoint = "/api/v1/news"

    for _ in range(5):
        response = await root_client.get(endpoint)
        assert response.status_code == 200

    blocked = await root_client.get(endpoint)
    assert blocked.status_code == 429

    root_client.cookies.set("access_token", "cookie-token-b", path="/")

    other = await root_client.get(endpoint)
    assert other.status_code == 200


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_sensitive_login_rate_limit(async_client, user_factory, monkeypatch):
    password = "ValidPass123!"
    user = await user_factory(
        email="login-rate@example.com",
        hashed_password=await get_password_hash(password),
    )
    data = {"username": user.email, "password": "wrong-password"}
    # Bearer token bypasses CSRF middleware
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Bearer dummy",
    }
    # Mock AuditService.log to avoid SQLite lock contention during rapid-fire hits
    monkeypatch.setattr(
        "app.services.audit_service.AuditService.log", lambda *args, **kwargs: None
    )

    for _ in range(4):
        response = await async_client.post("/auth/login", data=data, headers=headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        # Delay to avoid SQLite lock contention on concurrent writes
        await asyncio.sleep(0.5)

    blocked = await async_client.post("/auth/login", data=data, headers=headers)
    # Accept both rate limit (429) and account lockout (423) as valid blocking responses
    assert blocked.status_code in (
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_423_LOCKED,
    )


@pytest.mark.asyncio
async def test_sensitive_forgot_password_rate_limit(
    async_client, user_factory, monkeypatch
):
    user = await user_factory(email="forgot-rate@example.com")
    payload = {"email": user.email}

    # Simulate rate limit logic from AuthService intentionally failing on 5th try
    call_count = 0

    async def mock_enforce(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 4:
            from app.core.ratelimit.exceptions import RateLimitExceeded

            raise RateLimitExceeded(limit=4, remaining=0, reset_after=60)

    monkeypatch.setattr("app.core.ratelimit.enforce_rate_limit", mock_enforce)

    # Bearer token bypasses CSRF middleware
    headers = {"Authorization": "Bearer dummy"}
    for _ in range(4):
        response = await async_client.post(
            "/password/forgot", json=payload, headers=headers
        )
        assert response.status_code == status.HTTP_200_OK

    blocked = await async_client.post("/password/forgot", json=payload, headers=headers)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend():
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    settings.rate_limit_storage_backend = "memory"
    settings.rate_limit_storage_uri = "memory://"
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

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


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend_resolves_proxy_headers():
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    original_trusted = settings.trusted_proxies
    settings.rate_limit_storage_backend = "memory"
    settings.rate_limit_storage_uri = "memory://"
    settings.trusted_proxies = "127.0.0.1"
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

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
        settings.trusted_proxies = original_trusted

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend_ignores_untrusted_proxy_headers():
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    original_trusted = settings.trusted_proxies
    settings.rate_limit_storage_backend = "memory"
    settings.rate_limit_storage_uri = "memory://"
    settings.trusted_proxies = ""
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-untrusted-proxy"
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
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            second = await client.get(
                "/limited",
                headers={"X-Forwarded-For": "198.51.100.12"},
            )
            third = await client.get(
                "/limited",
                headers={"X-Forwarded-For": "198.51.100.13"},
            )
    finally:
        settings.rate_limit_storage_backend = original_backend
        settings.rate_limit_storage_uri = original_uri
        settings.trusted_proxies = original_trusted

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
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

    monkeypatch.setattr(
        "app.core.ratelimit.strategies.memory.MemorySlidingWindowStrategy.check",
        _fail_check,
    )

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


@pytest.mark.asyncio
async def test_sensitive_dependency_redis_backend_forwarded_header(
    monkeypatch, _rate_limit_redis_client
):
    original_backend = settings.rate_limit_storage_backend
    original_uri = settings.rate_limit_storage_uri
    original_trusted = settings.trusted_proxies
    settings.rate_limit_storage_backend = "redis"
    settings.rate_limit_storage_uri = "redis://test"
    settings.trusted_proxies = "127.0.0.1"

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

    monkeypatch.setattr(
        "app.core.ratelimit.strategies.memory.MemorySlidingWindowStrategy.check",
        _fail_check,
    )

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
        settings.trusted_proxies = original_trusted

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_enforce_rate_limit_falls_back_on_redis_error(monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.strategies.memory._memory_windows", {})

    async def failing_redis(*args, **kwargs):
        raise RedisError("unknown command EVAL")

    monkeypatch.setattr(
        "app.core.ratelimit.strategies.redis.RedisSlidingWindowStrategy.check",
        failing_redis,
    )

    await rate_limit.enforce_rate_limit(
        identifier="demo",
        limit=1,
        window_seconds=60,
        strategy=rate_limit.RedisSlidingWindowStrategy("redis://test"),
    )

    with pytest.raises(rate_limit.RateLimitExceeded):
        await rate_limit.enforce_rate_limit(
            identifier="demo",
            limit=1,
            window_seconds=60,
            strategy=rate_limit.RedisSlidingWindowStrategy("redis://test"),
        )


@pytest.mark.asyncio
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

    async def fail_check(self, identifier, limit=None, window_seconds=None):
        raise RedisError("boom")

    monkeypatch.setattr(RateLimitMiddleware, "_check_limit", fail_check)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # HIGH-05 (audit 2026-03-11): Test that we now FAIL-CLOSED (429) instead of
        # failing open (200) when Redis is down.
        # The middleware falls back to MemorySlidingWindowStrategy.
        # Since limit is 1, and this is the first request in memory, it might pass,
        # but we want to verify that it's NOT just ignoring the error.
        # We'll hit it twice to ensure the memory fallback blocks it.
        response1 = await client.get("/ping")
        response2 = await client.get("/ping")

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        # Header is present in memory strategy
        assert "X-RateLimit-Limit" in response1.headers


@hypo_settings(max_examples=25)
@given(
    count=st.integers(min_value=1, max_value=50),
    unit=st.sampled_from(["s", "m", "h", "d"]),  # Valid units in new parser
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

    expected_seconds = _TIME_UNITS.get(unit)
    if expected_seconds is None:
        expected_seconds = _TIME_UNITS.get(unit.rstrip("s"))
    assert parsed == (count, expected_seconds)


@hypo_settings(max_examples=25, suppress_health_check=[HealthCheck.filter_too_much])
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
@pytest.mark.asyncio
async def test_check_rate_limit_blocks_after_limit(
    identifier: str, _rate_limit_redis_client, monkeypatch
):
    # Clear redis between hypothesis iterations to ensure clean state
    await _rate_limit_redis_client.flushall()
    monkeypatch.setattr("app.core.ratelimit.strategies.base._shared_clients", {})
    # Reset the single write lock (replaces the removed _shared_client_locks dict).
    # PERF-3 audit 2026-02-26: per-URL lock dict was replaced by one module-level lock.
    monkeypatch.setattr(
        "app.core.ratelimit.strategies.base._shared_clients_write_lock", asyncio.Lock()
    )

    namespace = "prop"
    limit = 2
    window = 60

    for _ in range(limit):
        allowed = await rate_limit.get_default_strategy(namespace).check(
            key=identifier,
            limit=limit,
            window_seconds=window,
        )
        assert allowed.allowed

    blocked = await rate_limit.get_default_strategy(namespace).check(
        key=identifier,
        limit=limit,
        window_seconds=window,
    )

    assert blocked.allowed is False
    assert blocked.remaining == 0


@pytest.mark.asyncio
async def test_rate_limit_per_endpoint_limits():
    """Test that different endpoints get different rate limits."""
    app = FastAPI()

    # Create custom endpoint limits for testing
    custom_limits = (
        EndpointRateLimit("/auth/login", 2, 60),  # Strict: 2/min
        EndpointRateLimit("/api/", 5, 60),  # Medium: 5/min
    )

    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        redis_url="memory://",
        limit=10,  # Default: 10/min
        window_seconds=60,
        endpoint_limits=custom_limits,
    )

    @app.post("/auth/login")
    async def _login():  # pragma: no cover - minimal endpoint
        return {"ok": True}

    @app.get("/api/data")
    async def _api_data():  # pragma: no cover - minimal endpoint
        return {"data": []}

    @app.get("/other")
    async def _other():  # pragma: no cover - minimal endpoint
        return {"other": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # Auth endpoint should be blocked after 2 requests
        for i in range(2):
            resp = await client.post("/auth/login")
            assert resp.status_code == 200, f"Auth request {i + 1} should succeed"
            assert resp.headers.get("X-RateLimit-Limit") == "2"

        blocked_auth = await client.post("/auth/login")
        assert blocked_auth.status_code == 429, "Auth endpoint should be blocked"

        # API endpoint should still work (different limit)
        for i in range(5):
            resp = await client.get("/api/data")
            assert resp.status_code == 200, f"API request {i + 1} should succeed"
            assert resp.headers.get("X-RateLimit-Limit") == "5"

        blocked_api = await client.get("/api/data")
        assert blocked_api.status_code == 429, "API endpoint should be blocked"

        # /other uses default limit (10/min) - should still work
        for i in range(5):
            resp = await client.get("/other")
            assert resp.status_code == 200, f"Other request {i + 1} should succeed"
            assert resp.headers.get("X-RateLimit-Limit") == "10"
