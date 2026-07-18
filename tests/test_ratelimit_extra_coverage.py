"""Extra unit tests to close remaining coverage gaps in ratelimit module."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from app.core.config import settings
from app.core.ratelimit.exceptions import RateLimitStorageUnavailable
from app.core.ratelimit.fastapi import (
    get_progressive_delay_tracker,
    sensitive_route_limit,
)
from app.core.ratelimit.logic import (
    check_rate_limit,
    enforce_rate_limit,
    get_default_strategy,
)
from app.core.ratelimit.middleware import RateLimitMiddleware
from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import (
    _extract_ip_from_forwarded,
    _normalize_ip,
    extract_user_id_for_ratelimit,
    parse_rate_limit,
    resolve_client_ip,
)

# ── 1. parse_rate_limit edge cases ──────────────────────────────────────────


def test_parse_rate_limit_edge_cases():
    fallback = (10, 60)
    # line 44: value is empty string after strip
    assert parse_rate_limit("   ", fallback=fallback) == fallback
    # line 50: len(parts) != 2
    assert parse_rate_limit("5 minute second", fallback=fallback) == fallback
    assert parse_rate_limit("5 per minute per second", fallback=fallback) == fallback
    # line 56-57: count is not an integer
    assert parse_rate_limit("invalid_count / minute", fallback=fallback) == fallback
    # line 62-65: unit_raw is not an integer and not a valid unit name
    assert parse_rate_limit("5 / invalidunit", fallback=fallback) == fallback
    # line 68: count <= 0 or seconds <= 0
    assert parse_rate_limit("0 / minute", fallback=fallback) == fallback
    assert parse_rate_limit("5 / -10", fallback=fallback) == fallback


# ── 2. _normalize_ip edge cases ─────────────────────────────────────────────


def test_normalize_ip_edge_cases():
    # line 75: empty string
    assert _normalize_ip("") is None
    assert _normalize_ip("   ") is None
    # line 78-79: invalid IP address
    assert _normalize_ip("invalid-ip") is None
    assert _normalize_ip("999.999.999.999") is None


# ── 3. _extract_ip_from_forwarded edge cases ────────────────────────────────


def test_extract_ip_from_forwarded_edge_cases():
    # line 84-89: parts without for=
    assert _extract_ip_from_forwarded("by=127.0.0.1; proto=https") is None
    assert _extract_ip_from_forwarded("for=; proto=https") == ""


# ── 4. resolve_client_ip edge cases ─────────────────────────────────────────


def test_resolve_client_ip_edge_cases(monkeypatch):
    # Setup trusted proxies
    monkeypatch.setattr(settings, "trusted_proxies_list", ["127.0.0.1"])

    # Mock request
    mock_request = MagicMock()
    mock_request.client = MagicMock(host="127.0.0.1")

    # 103->111: xfwd is false, checks Forwarded
    mock_request.headers = {"Forwarded": "for=203.0.113.195"}
    assert resolve_client_ip(mock_request) == "203.0.113.195"

    # 104->111: xfwd is true, but no candidate found (e.g. invalid IP)
    mock_request.headers = {
        "X-Forwarded-For": "invalid-ip",
        "Forwarded": "for=203.0.113.195",
    }
    # 106->104: candidate is falsy, continues loop
    assert resolve_client_ip(mock_request) == "203.0.113.195"

    # 113->116: Forwarded header is absent, return ip or normalized_client
    mock_request.headers = {"X-Forwarded-For": "invalid-ip"}
    assert resolve_client_ip(mock_request) == "127.0.0.1"


# ── 5. extract_user_id_for_ratelimit exception ──────────────────────────────


def test_extract_user_id_for_ratelimit_exception():
    mock_request = MagicMock()
    mock_request.headers = {"authorization": "Bearer invalid_token"}
    mock_request.cookies = {}

    # decode_token should raise exception, return None (lines 154-155)
    with patch("app.auth.security.decode_token", side_effect=Exception("Decode error")):
        assert extract_user_id_for_ratelimit(mock_request) is None


# ── 6. sensitive_route_limit ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sensitive_route_limit_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    dependency = sensitive_route_limit(limit=1, window_sec=60)
    mock_request = MagicMock()
    # Should return early (line 44)
    await dependency(mock_request)


@pytest.mark.asyncio
async def test_sensitive_route_limit_invalid_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    dependency = sensitive_route_limit(limit=0, window_sec=60)
    mock_request = MagicMock()
    # Should return early (line 47)
    await dependency(mock_request)


@pytest.mark.asyncio
async def test_sensitive_route_limit_user_key(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")

    dependency = sensitive_route_limit(limit=2, window_sec=60)
    mock_request = MagicMock()
    mock_request.url.path = "/test-route"

    # 57: user_id format path
    with patch(
        "app.core.ratelimit.fastapi.extract_user_id_for_ratelimit",
        return_value="user_123",
    ):
        # Let's verify that we call enforce_rate_limit with correct key prefix
        with patch(
            "app.core.ratelimit.fastapi.enforce_rate_limit", new_callable=AsyncMock
        ) as mock_enforce:
            await dependency(mock_request)
            mock_enforce.assert_called_once()
            assert "user:user_123" in mock_enforce.call_args[1]["identifier"]


@pytest.mark.asyncio
async def test_sensitive_route_limit_redis_backend(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://test")

    dependency = sensitive_route_limit(limit=2, window_sec=60)
    mock_request = MagicMock()
    mock_request.url.path = "/test-route"

    with patch(
        "app.core.ratelimit.fastapi.enforce_rate_limit", new_callable=AsyncMock
    ) as mock_enforce:
        await dependency(mock_request)
        mock_enforce.assert_called_once()
        # line 65: should construct RedisSlidingWindowStrategy
        assert isinstance(
            mock_enforce.call_args[1]["strategy"], RedisSlidingWindowStrategy
        )


@pytest.mark.asyncio
async def test_sensitive_route_limit_storage_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://test")

    dependency = sensitive_route_limit(limit=2, window_sec=60)
    mock_request = MagicMock()
    mock_request.url.path = "/test-route"

    # Raise RateLimitStorageUnavailable (lines 91-93)
    with patch(
        "app.core.ratelimit.fastapi.enforce_rate_limit",
        side_effect=RateLimitStorageUnavailable("error"),
    ):
        with pytest.raises(RateLimitStorageUnavailable):
            await dependency(mock_request)


# ── 7. get_progressive_delay_tracker exception ──────────────────────────────


def test_get_progressive_delay_tracker_exception(monkeypatch):
    # line 106-110: raise settings error, verify None is used
    with patch("app.core.ratelimit.fastapi.settings", None):
        tracker = get_progressive_delay_tracker()
        assert tracker._redis_url is None


# ── 8. check_rate_limit ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_rate_limit_redis_success(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    # Mock Redis strategy and circuit breaker
    mock_strategy = MagicMock()
    mock_strategy.check = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=4, retry_after=0)
    )

    mock_cb = MagicMock()
    mock_cb.allow_request.return_value = True

    with patch(
        "app.core.ratelimit.logic._get_redis_strategy", return_value=mock_strategy
    ):
        with patch(
            "app.core.ratelimit.logic.get_circuit_breaker", return_value=mock_cb
        ):
            res = await check_rate_limit(
                identifier="user_123",
                limit=5,
                window_seconds=60,
                redis_url="redis://localhost",
            )
            # lines 89-90: cb.record_success() and return result
            mock_cb.record_success.assert_called_once()
            assert res.allowed is True


@pytest.mark.asyncio
async def test_check_rate_limit_circuit_open(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    mock_cb = MagicMock()
    mock_cb.allow_request.return_value = False
    mock_cb.state.name = "OPEN"

    with patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=mock_cb):
        res = await check_rate_limit(
            identifier="user_123",
            limit=5,
            window_seconds=60,
            redis_url="redis://localhost",
        )
        # line 98: should log circuit open debug log, and check fallback memory
        assert res.allowed is True  # fallback memory allowed it


def test_get_default_strategy_redis(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "redis://localhost")

    # line 117: check it returns RedisStrategy
    with patch("app.core.ratelimit.logic._get_redis_strategy") as mock_get_redis:
        get_default_strategy()
        mock_get_redis.assert_called_once_with("redis://localhost")


@pytest.mark.asyncio
async def test_enforce_rate_limit_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    # line 131: returns early with allowed=True
    info = await enforce_rate_limit(
        identifier="user_123", limit=5, window_seconds=60, strategy=MagicMock()
    )
    assert info.allowed is True


@pytest.mark.asyncio
async def test_enforce_rate_limit_circuit_open(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    mock_cb = MagicMock()
    mock_cb.allow_request.return_value = False

    with patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=mock_cb):
        # lines 157-159: circuit open — skip Redis entirely, use fallback
        info = await enforce_rate_limit(
            identifier="user_123", limit=5, window_seconds=60, strategy=MagicMock()
        )
        assert info.allowed is True


# ── 9. RateLimitMiddleware ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_middleware_non_http_scope():
    middleware = RateLimitMiddleware(AsyncMock())
    scope = {"type": "websocket"}
    # line 68-69: type != "http"
    await middleware(scope, AsyncMock(), AsyncMock())
    middleware._app.assert_called_once_with(scope, ANY, ANY)


@pytest.mark.asyncio
async def test_middleware_double_failure():
    # primary is memory, but check_limit fails (raises exception)
    middleware = RateLimitMiddleware(
        app=AsyncMock(), storage_backend="memory", limit=2, window_seconds=60
    )

    async def failing_check(*args, **kwargs):
        raise RuntimeError("Primary failure")

    middleware._check_limit = failing_check

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/limited",
        "headers": [],
        "query_string": b"",
    }

    sent_messages = []

    async def mock_send(message):
        sent_messages.append(message)

    # line 122-136: should fail-closed with 503
    await middleware(scope, AsyncMock(), mock_send)
    assert len(sent_messages) > 0
    assert sent_messages[0]["status"] == 503


@pytest.mark.asyncio
async def test_middleware_headers_disabled_when_blocked():
    middleware = RateLimitMiddleware(
        app=AsyncMock(),
        storage_backend="memory",
        limit=1,
        window_seconds=60,
        headers_enabled=False,
    )

    # Block first request
    mock_strategy = MagicMock()
    mock_strategy.check = AsyncMock(
        return_value=RateLimitInfo(allowed=False, remaining=0, retry_after=30)
    )
    middleware._strategy = mock_strategy

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/limited",
        "headers": [],
        "query_string": b"",
    }

    # Capture sent messages
    sent_messages = []

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(scope, AsyncMock(), mock_send)
    # line 147->154: should return problem details without X-RateLimit headers
    assert len(sent_messages) > 0
    assert sent_messages[0]["status"] == 429
    body = sent_messages[1]["body"].decode()
    assert "Rate Limit Exceeded" in body


@pytest.mark.asyncio
async def test_middleware_existing_headers():
    # Test middleware where headers already exist in response
    # line 175->177 and 177->181
    async def app_returning_headers(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"x-ratelimit-limit", b"999"),
                    (b"x-ratelimit-remaining", b"999"),
                ],
            }
        )

    middleware = RateLimitMiddleware(
        app=app_returning_headers,
        storage_backend="memory",
        limit=2,
        window_seconds=60,
        headers_enabled=True,
    )

    mock_strategy = MagicMock()
    mock_strategy.check = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=1, retry_after=0)
    )
    middleware._strategy = mock_strategy

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/limited",
        "headers": [],
        "query_string": b"",
    }

    sent_messages = []

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(scope, AsyncMock(), mock_send)

    # Verify that existing headers (999) are preserved and not overwritten
    headers = dict(sent_messages[0]["headers"])
    assert headers[b"x-ratelimit-limit"] == b"999"
    assert headers[b"x-ratelimit-remaining"] == b"999"


@pytest.mark.asyncio
async def test_middleware_headers_disabled_allowed():
    # line 186
    middleware = RateLimitMiddleware(
        app=AsyncMock(),
        storage_backend="memory",
        limit=2,
        window_seconds=60,
        headers_enabled=False,
    )

    mock_strategy = MagicMock()
    mock_strategy.check = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=1, retry_after=0)
    )
    middleware._strategy = mock_strategy

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/limited",
        "headers": [],
        "query_string": b"",
    }

    await middleware(scope, MagicMock(), AsyncMock())
    middleware._app.assert_called_once_with(scope, ANY, ANY)


@pytest.mark.asyncio
async def test_middleware_empty_bearer_token():
    # line 209->213: token is empty after strip
    middleware = RateLimitMiddleware(AsyncMock())
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/limited",
        "headers": [(b"authorization", b"Bearer   ")],
        "query_string": b"",
    }
    # It should fallback to IP address formatting
    ident = middleware._build_identifier(Request(scope))
    assert ident.startswith("ip:")


@pytest.mark.asyncio
async def test_middleware_options_request():
    # line 228
    middleware = RateLimitMiddleware(AsyncMock())
    scope = {
        "type": "http",
        "method": "OPTIONS",
        "path": "/limited",
        "headers": [],
        "query_string": b"",
    }
    await middleware(scope, AsyncMock(), AsyncMock())
    middleware._app.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_health_path_skipped():
    # line 233
    middleware = RateLimitMiddleware(AsyncMock())
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/healthz",
        "headers": [],
        "query_string": b"",
    }
    await middleware(scope, AsyncMock(), AsyncMock())
    middleware._app.assert_called_once()


@pytest.mark.asyncio
async def test_get_shared_client_concurrent():
    import app.core.ratelimit.strategies.base as base_module
    from app.core.ratelimit.strategies.base import (
        get_shared_client,
        set_rate_limit_client_factory,
    )

    # Mock redis factory to return mock clients
    mock_factory = MagicMock()
    set_rate_limit_client_factory(mock_factory)

    try:
        # Force bootstrap of the lock by making one dummy request
        await get_shared_client("redis://localhost:8888")

        # Now acquire the lock manually
        lock = base_module._shared_clients_write_lock
        assert lock is not None
        await lock.acquire()

        # Start concurrent client retrievals (both will check line 37, find None, and block on lock)
        t1 = get_shared_client("redis://localhost:9999")
        t2 = get_shared_client("redis://localhost:9999")

        # Yield to let them execute up to the locked line 45
        task1 = asyncio.create_task(t1)
        task2 = asyncio.create_task(t2)
        await asyncio.sleep(0.01)

        # Release the lock so they can proceed
        lock.release()

        # Wait for both to complete
        c1 = await task1
        c2 = await task2

        assert c1 is c2
        assert mock_factory.call_count == 2  # one for 8888, one for 9999
    finally:
        set_rate_limit_client_factory(None)
