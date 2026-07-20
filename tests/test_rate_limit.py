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
from app.core.ratelimit import EndpointRateLimit, RateLimitMiddleware
from app.core.ratelimit.utils import _TIME_UNITS


@pytest.fixture(autouse=True)
def enable_rate_limiting(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)


@pytest.mark.asyncio
async def test_rate_limit_per_ip():
    """Test using a public endpoint that is NOT exempted."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        limit=5,
        window_seconds=60,
    )

    @app.get("/api/v1/news")
    async def _news():
        return {"data": []}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        endpoint = "/api/v1/news"
        for _ in range(5):
            response = await client.get(endpoint)
            assert response.status_code == 200
            assert response.headers.get("X-RateLimit-Limit") == "5"

        response = await client.get(endpoint)
        assert response.status_code == 429


@pytest.mark.asyncio
async def test_health_check_exempted(root_client):
    """Test that health check is exempted from rate limits."""
    for _ in range(20):
        response = await root_client.get("/healthz")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers


@pytest.mark.asyncio
async def test_rate_limit_per_token():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        limit=5,
        window_seconds=60,
    )

    @app.get("/api/v1/news")
    async def _news():
        return {"data": []}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        headers = {"Authorization": "Bearer token-a"}
        endpoint = "/api/v1/news"
        for _ in range(5):
            response = await client.get(endpoint, headers=headers)
            assert response.status_code == 200
        blocked = await client.get(endpoint, headers=headers)
        assert blocked.status_code == 429

        other = await client.get(endpoint, headers={"Authorization": "Bearer token-b"})
        assert other.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_per_cookie():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        limit=5,
        window_seconds=60,
    )

    @app.get("/api/v1/news")
    async def _news():
        return {"data": []}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        client.cookies.set("access_token_v2", "cookie-token-a", path="/")
        endpoint = "/api/v1/news"

        for _ in range(5):
            response = await client.get(endpoint)
            assert response.status_code == 200

        blocked = await client.get(endpoint)
        assert blocked.status_code == 429

        client.cookies.set("access_token_v2", "cookie-token-b", path="/")

        other = await client.get(endpoint)
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
    async def _static() -> Response:
        return Response(content=b"", media_type="image/png")

    @app.get("/media/example.png")
    async def _media() -> Response:
        return Response(content=b"", media_type="image/png")

    @app.get("/storage/example.png")
    async def _storage() -> Response:
        return Response(content=b"", media_type="image/png")

    @app.get("/assets/app.js")
    async def _assets() -> Response:
        return Response(content=b"console.log('hi');", media_type="text/javascript")

    @app.get("/limited")
    async def _limited():
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
async def test_sensitive_login_rate_limit(
    async_client, user_factory, db_session, monkeypatch
):
    import uuid

    password = "ValidPass123!"
    # Use a unique email per test run to avoid rate limit state pollution from parallel tests
    unique_email = f"login-rate-{uuid.uuid4().hex[:8]}@example.com"
    user = await user_factory(
        email=unique_email,
        hashed_password=await get_password_hash(password),
    )
    data = {"username": user.email, "password": "wrong-password"}
    # Only Content-Type header needed — the async_client fixture pre-configures CSRF.
    # Do NOT use 'Authorization: Bearer dummy' as it causes JWT middleware to
    # reject requests with 401 before the login handler can track failed attempts.
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Reset in-memory rate limit state so that prior tests' requests to /auth/login
    # (with IP 127.0.0.1) don't prematurely trigger the sensitive-route rate limiter
    # and block our attempts with 429 before the lockout mechanism fires with 423.
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

    # Mock AuditService.log to avoid SQLite lock contention during rapid-fire hits
    monkeypatch.setattr(
        "app.services.audit_service.AuditService.log", lambda *args, **kwargs: None
    )
    # Mock the lockout alert email task (it tries to connect to SMTP in testing)
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.tasks.email.send_lockout_alert.kick", AsyncMock())

    # Send 4 failed attempts — the default threshold is 5:30.
    # On the 5th attempt, the login service registers it (now 5 total),
    # triggers the lockout (triggered=True), and returns 423 Locked.
    for _ in range(4):
        response = await async_client.post("/auth/login", data=data, headers=headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # The 5th attempt triggers lockout (or rate limit) — both 429 and 423 are valid
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
            from app.core.ratelimit.models import RateLimitInfo

            raise RateLimitExceeded(
                RateLimitInfo(allowed=False, remaining=0, retry_after=60)
            )

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
    async def _ping():
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
async def test_middleware_double_failure_503():
    """Lines 119-136: When storage_backend is 'memory' and _check_limit raises,
    the middleware's else branch returns 503 (double failure path).

    The else-branch at line 119 handles non-redis backends: if _check_limit raises
    any exception AND the backend is not 'redis', there's no Redis fallback,
    so the middleware fails-closed with 503 (RZ-27-03).
    """
    import unittest.mock

    import httpx
    from fastapi import FastAPI

    from app.core.ratelimit.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",  # non-redis → double-failure else branch
        redis_url="",
        limit=100,
        window_seconds=60,
    )

    @app.get("/boom")
    async def _boom():
        return {"ok": True}

    async def raise_error(self_or_identifier, *args, **kwargs):
        raise OSError("Memory strategy completely failed")

    # Patch at class level so all instances use the failing _check_limit
    with unittest.mock.patch.object(RateLimitMiddleware, "_check_limit", raise_error):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/boom")

    # Should return 503 (double failure: memory backend failed, no Redis fallback)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Service temporarily unavailable" in response.text


@pytest.mark.asyncio
async def test_middleware_redis_fallback_exceeded_log():
    """Lines 113-118: When Redis fallback strategy is also exceeded,
    the middleware logs ERROR 'Rate limit exceeded (fallback-mode)'.

    When storage_backend='redis', _check_limit raises, AND the fallback memory strategy
    also reports rate limit exceeded, the error log at line 114 is triggered.
    """
    import httpx
    from fastapi import FastAPI

    from app.core.ratelimit.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="redis",
        redis_url="redis://localhost:6379",
        limit=1,  # Very low limit for fallback (fallback_limit = max(1//2, 1) = 1)
        window_seconds=60,
    )

    @app.get("/limited")
    async def _limited():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # Find and patch _check_limit on the Redis middleware instance
        current = app.middleware_stack
        while current is not None:
            if isinstance(current, RateLimitMiddleware):
                request_count = 0

                async def failing_then_exceeded(identifier, limit, window):
                    nonlocal request_count
                    request_count += 1
                    if request_count <= 2:
                        raise OSError("Redis down")
                    # On 3rd+ call, return exceeded from fallback
                    from app.core.ratelimit.models import RateLimitInfo

                    return RateLimitInfo(allowed=False, remaining=0, retry_after=60)

                current._check_limit = failing_then_exceeded  # type: ignore[method-assign]
                break
            current = getattr(current, "app", None)

        # First call: Redis fails → fallback at 50% limit (1 req/min)
        # Fallback limit = max(1//2, 1) = 1
        resp1 = await client.get("/limited")
        assert resp1.status_code == status.HTTP_200_OK  # 1st fallback allowed

        # Second call: Redis fails → fallback already used → exceeded → 429
        resp2 = await client.get("/limited")
        assert resp2.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_middleware_head_static_path_returns_200():
    """Lines 75-78: HEAD requests on static-like paths return 200 without calling app.

    When `method == 'HEAD'` AND `_is_static_like_path(path)` is True, the middleware
    returns a 200 response WITHOUT calling the inner app.
    """
    import httpx
    from fastapi import FastAPI

    from app.core.ratelimit.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        storage_backend="memory",
        limit=100,
        window_seconds=60,
    )

    @app.head("/static/image.png")
    async def _head_static():
        raise Exception("Inner app should NOT be called for static HEAD")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.head("/static/image.png")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-dep"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first = await client.get("/limited")
        second = await client.get("/limited")
        third = await client.get("/limited")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend_resolves_proxy_headers(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-proxy"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)

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

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_sensitive_dependency_memory_backend_ignores_untrusted_proxy_headers(
    monkeypatch,
):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "trusted_proxies", "")
    ratelimit_module.clear_memory_state()
    ratelimit_module.clear_delay_memory()

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="memory-untrusted-proxy"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)

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

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.skip(
    reason="Requires real Redis for Lua scripting — FakeRedis does not support EVAL"
)
@pytest.mark.asyncio
async def test_sensitive_dependency_redis_backend(
    monkeypatch, _rate_limit_redis_client
):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://test")

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="redis-dep"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():
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

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first = await client.get("/limited")
        second = await client.get("/limited")
        third = await client.get("/limited")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.headers.get("Retry-After") is not None


@pytest.mark.skip(
    reason="Requires real Redis for Lua scripting — FakeRedis does not support EVAL"
)
@pytest.mark.asyncio
async def test_sensitive_dependency_redis_backend_forwarded_header(
    monkeypatch, _rate_limit_redis_client
):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://test")
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")

    dependency = ratelimit_module.sensitive_route_limit(
        limit=2, window_sec=60, key_prefix="redis-proxy"
    )

    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(dependency)])
    async def _limited():
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
    async def _ping():
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
    # Clear redis AND in-memory state between hypothesis iterations
    await _rate_limit_redis_client.flushall()
    from app.core.ratelimit import clear_memory_state

    clear_memory_state()
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
    async def _login():
        return {"ok": True}

    @app.get("/api/data")
    async def _api_data():
        return {"data": []}

    @app.get("/other")
    async def _other():
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


@pytest.mark.asyncio
async def test_fastapi_ratelimit_additional_coverage(monkeypatch):
    from unittest.mock import patch

    # 1. Test resolved_limit <= 0 or resolved_window <= 0
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    dependency = ratelimit_module.sensitive_route_limit(limit=0, window_sec=60)
    app = FastAPI()

    @app.get("/test-zero-limit", dependencies=[Depends(dependency)])
    async def _test_zero():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        resp = await client.get("/test-zero-limit")
        assert resp.status_code == 200

    # 2. Test user_id extracted from JWT
    with patch(
        "app.core.ratelimit.fastapi.extract_user_id_for_ratelimit",
        return_value="user123",
    ):
        dependency = ratelimit_module.sensitive_route_limit(limit=1, window_sec=60)
        app2 = FastAPI()

        @app2.get("/test-user-limit", dependencies=[Depends(dependency)])
        async def _test_user():
            return {"ok": True}

        transport2 = httpx.ASGITransport(app=app2)
        async with httpx.AsyncClient(
            transport=transport2, base_url="http://testserver"
        ) as client:
            resp1 = await client.get("/test-user-limit")
            assert resp1.status_code == 200

    # 3. Test RedisSlidingWindowStrategy configuration
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://localhost:6379/0")
    with patch(
        "app.core.ratelimit.fastapi.RedisSlidingWindowStrategy"
    ) as mock_redis_strategy:
        mock_instance = MagicMock()
        mock_instance.check = AsyncMock(
            return_value=ratelimit_module.RateLimitInfo(
                allowed=True, remaining=1, retry_after=0
            )
        )
        mock_redis_strategy.return_value = mock_instance
        dependency = ratelimit_module.sensitive_route_limit(limit=1, window_sec=60)
        app3 = FastAPI()

        @app3.get("/test-redis-limit", dependencies=[Depends(dependency)])
        async def _test_redis():
            return {"ok": True}

        transport3 = httpx.ASGITransport(app=app3)
        async with httpx.AsyncClient(
            transport=transport3, base_url="http://testserver"
        ) as client:
            await client.get("/test-redis-limit")
            mock_redis_strategy.assert_called_once_with("redis://localhost:6379/0")

    # 4. Test RateLimitStorageUnavailable propagation
    from app.core.ratelimit.exceptions import RateLimitStorageUnavailable

    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    with patch(
        "app.core.ratelimit.fastapi.enforce_rate_limit",
        side_effect=RateLimitStorageUnavailable("Storage offline"),
    ):
        dependency = ratelimit_module.sensitive_route_limit(limit=1, window_sec=60)
        app4 = FastAPI()

        @app4.get("/test-unavailable-limit", dependencies=[Depends(dependency)])
        async def _test_unavailable():
            return {"ok": True}

        transport4 = httpx.ASGITransport(app=app4)
        async with httpx.AsyncClient(
            transport=transport4, base_url="http://testserver"
        ) as client:
            with pytest.raises(RateLimitStorageUnavailable):
                await client.get("/test-unavailable-limit")

    # 5. Test get_progressive_delay_tracker settings exception
    with patch("app.core.ratelimit.fastapi.settings", new=None):
        tracker = ratelimit_module.get_progressive_delay_tracker()
        assert tracker._redis_url is None

    # 6. Test rate limit disabled
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    dependency = ratelimit_module.sensitive_route_limit(limit=1, window_sec=60)
    app5 = FastAPI()

    @app5.get("/test-disabled-limit", dependencies=[Depends(dependency)])
    async def _test_disabled():
        return {"ok": True}

    transport5 = httpx.ASGITransport(app=app5)
    async with httpx.AsyncClient(
        transport=transport5, base_url="http://testserver"
    ) as client:
        resp = await client.get("/test-disabled-limit")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# resolve_client_ip — trusted proxy paths (covers lines 100-116 in utils.py)
# ---------------------------------------------------------------------------


def test_resolve_client_ip_trusted_proxy_x_forwarded_for(monkeypatch):
    """Lines 100-108: When client IP is in trusted_proxies_list, use X-Forwarded-For."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import resolve_client_ip

    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "192.168.1.100, 10.0.0.1",
        "Forwarded": None,
    }.get(header)

    ip = resolve_client_ip(request)
    # Should use the first valid IP from X-Forwarded-For
    assert ip == "192.168.1.100"


def test_resolve_client_ip_trusted_proxy_forwarded_header(monkeypatch):
    """Lines 111-114: When X-Forwarded-For is absent, use RFC 7239 Forwarded header."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import resolve_client_ip

    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": None,
        "Forwarded": "for=203.0.113.10;proto=http",
    }.get(header)

    ip = resolve_client_ip(request)
    assert ip == "203.0.113.10"


def test_resolve_client_ip_trusted_proxy_invalid_x_forwarded_for(monkeypatch):
    """Lines 103->111: X-Forwarded-For with no valid IPs falls through to Forwarded header."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import resolve_client_ip

    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    request = MagicMock()
    request.client.host = "10.0.0.1"
    # X-Forwarded-For has only invalid IPs
    request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "not-an-ip, also-invalid",
        "Forwarded": "for=10.0.0.2",
    }.get(header)

    ip = resolve_client_ip(request)
    # Falls through to Forwarded header
    assert ip == "10.0.0.2"


def test_resolve_client_ip_not_trusted(monkeypatch):
    """Line 100: When client IP is NOT in trusted_proxies_list, use direct client IP."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import resolve_client_ip

    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    request = MagicMock()
    request.client.host = "192.168.1.50"  # Not in trusted proxies
    request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "1.2.3.4",
    }.get(header)

    ip = resolve_client_ip(request)
    # Should use the direct client IP, not X-Forwarded-For
    assert ip == "192.168.1.50"


def test_resolve_client_ip_no_client(monkeypatch):
    """Line 94: When request.client is None, uses 'unknown' as client host."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import resolve_client_ip

    monkeypatch.setattr(settings, "trusted_proxies_list", [])

    request = MagicMock()
    request.client = None
    request.headers.get = lambda header, default=None: None

    ip = resolve_client_ip(request)
    assert ip == "unknown"


def _mock_security_module(decode_token_val):
    import sys
    from contextlib import contextmanager
    from types import ModuleType

    @contextmanager
    def _inner():
        original = sys.modules.get("app.auth.security")
        mock_module = ModuleType("app.auth.security")
        mock_module.decode_token = decode_token_val

        class SecurityError(Exception):
            pass

        mock_module.SecurityError = SecurityError
        sys.modules["app.auth.security"] = mock_module
        try:
            yield
        finally:
            if original is not None:
                sys.modules["app.auth.security"] = original
            else:
                sys.modules.pop("app.auth.security", None)

    return _inner()


def test_extract_user_id_for_ratelimit_exception_path():
    """Lines 154-155: Exception in decode_token returns None (fail-closed)."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import extract_user_id_for_ratelimit

    request = MagicMock()
    request.headers.get = lambda header, default="": "Bearer sometoken"
    request.cookies.get = lambda header: None

    def raise_exc(token):
        raise Exception("JWT error")

    with _mock_security_module(raise_exc):
        result = extract_user_id_for_ratelimit(request)
    assert result is None


def test_extract_user_id_for_ratelimit_from_cookie():
    """Lines 142-153: Falls back to cookie when no Authorization header."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import extract_user_id_for_ratelimit

    request = MagicMock()
    request.headers.get = lambda header, default="": ""  # No auth header
    request.cookies.get = lambda header: "cookie_token"

    with _mock_security_module(lambda token: {"sub": "user-123"}):
        result = extract_user_id_for_ratelimit(request)
    assert result == "user-123"


def test_extract_user_id_for_ratelimit_none_sub():
    """Line 153: When sub is None or empty, returns None."""
    from unittest.mock import MagicMock

    from app.core.ratelimit.utils import extract_user_id_for_ratelimit

    request = MagicMock()
    request.headers.get = lambda header, default="": "Bearer token"
    request.cookies.get = lambda header: None

    with _mock_security_module(lambda token: {"sub": None}):
        result = extract_user_id_for_ratelimit(request)
    assert result is None
