"""Deterministic unit coverage for ratelimit utility and middleware edges."""

from __future__ import annotations

import hashlib
import ipaddress
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.config import settings
from app.core.ratelimit import utils as ratelimit_utils
from app.core.ratelimit.middleware import RateLimitMiddleware
from app.core.ratelimit.models import EndpointRateLimit, RateLimitInfo
from app.core.ratelimit.utils import (
    _normalize_ip_obj,
    _parse_trusted_proxies,
    extract_user_id_for_ratelimit,
    parse_rate_limit,
    resolve_client_ip,
)


def _proxy_request(
    host: str | None,
    headers: dict[str, str] | None = None,
) -> SimpleNamespace:
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client, headers=Headers(headers or {}))


def _http_scope(
    *,
    path: str = "/limited",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, object]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "scheme": "http",
        "server": ("testserver", 80),
        "http_version": "1.1",
    }


def test_ratelimit_utils_parse_and_proxy_type_edges():
    assert parse_rate_limit(None, fallback=(10, 60)) == (10, 60)
    assert _normalize_ip_obj(None) is None

    networks = _parse_trusted_proxies(
        [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_address("192.0.2.1"),
            "198.51.100.0/24",
            "",
        ]
    )
    assert networks == [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("192.0.2.1/32"),
        ipaddress.ip_network("198.51.100.0/24"),
    ]


def test_ratelimit_utils_proxy_parse_fallback_and_invalid_item():
    fallback_network = ipaddress.ip_network("192.0.2.9/32")
    with (
        patch.object(
            ratelimit_utils.ipaddress,
            "ip_network",
            side_effect=[ValueError("not a network"), fallback_network],
        ),
        patch.object(
            ratelimit_utils.ipaddress,
            "ip_address",
            return_value=ipaddress.ip_address("192.0.2.9"),
        ),
    ):
        assert _parse_trusted_proxies(["proxy-address"]) == [fallback_network]

    with (
        patch.object(
            ratelimit_utils.ipaddress,
            "ip_network",
            side_effect=ValueError("not a network"),
        ),
        patch.object(
            ratelimit_utils.ipaddress,
            "ip_address",
            side_effect=ValueError("not an address"),
        ),
    ):
        assert _parse_trusted_proxies(["invalid-proxy"]) == []


def test_resolve_client_ip_covers_forwarded_proxy_boundaries(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies_list", ["127.0.0.0/8"])

    request = _proxy_request(
        "127.0.0.1",
        {"X-Forwarded-For": "invalid, 192.0.2.10, 127.0.0.2"},
    )
    assert resolve_client_ip(request) == "192.0.2.10"

    all_trusted = _proxy_request(
        "127.0.0.1",
        {"X-Forwarded-For": "127.0.0.2, 127.0.0.3"},
    )
    assert resolve_client_ip(all_trusted) == "127.0.0.2"

    forwarded = _proxy_request(
        "127.0.0.1",
        {"Forwarded": "for=invalid;proto=https, for=127.0.0.4"},
    )
    assert resolve_client_ip(forwarded) == "127.0.0.4"

    no_valid_forwarded = _proxy_request(
        "127.0.0.1",
        {"Forwarded": "for=invalid;proto=https"},
    )
    assert resolve_client_ip(no_valid_forwarded) == "127.0.0.1"


def test_extract_user_id_without_authentication_returns_none():
    request = SimpleNamespace(headers=Headers({}), cookies={})
    assert extract_user_id_for_ratelimit(request) is None


@pytest.mark.asyncio
async def test_middleware_head_static_path_returns_empty_success():
    app = AsyncMock()
    middleware = RateLimitMiddleware(app, storage_backend="memory")
    sent: list[dict[str, object]] = []
    send = AsyncMock(side_effect=sent.append)

    await middleware(
        _http_scope(path="/static/app.js", method="HEAD"),
        AsyncMock(),
        send,
    )

    assert sent[0]["status"] == 200
    app.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_redis_failure_uses_stricter_memory_fallback(monkeypatch):
    app = AsyncMock()
    middleware = RateLimitMiddleware(
        app,
        storage_backend="redis",
        redis_url="redis://test",
        limit=4,
        window_seconds=60,
    )
    middleware._check_limit = AsyncMock(side_effect=RuntimeError("redis offline"))
    fallback_info = RateLimitInfo(allowed=False, remaining=0, retry_after=7)
    fallback_check = AsyncMock(return_value=fallback_info)
    monkeypatch.setattr(
        "app.core.ratelimit.middleware.MemorySlidingWindowStrategy.check",
        fallback_check,
    )
    sent: list[dict[str, object]] = []
    send = AsyncMock(side_effect=sent.append)

    await middleware(_http_scope(), AsyncMock(), send)

    fallback_check.assert_awaited_once()
    assert fallback_check.await_args.args[1:] == (2, 60)
    assert sent[0]["status"] == 429
    assert dict(sent[0]["headers"])[b"X-RateLimit-Limit"] == b"4"


@pytest.mark.asyncio
async def test_middleware_redis_failure_fallback_can_allow_request(monkeypatch):
    app = AsyncMock()
    middleware = RateLimitMiddleware(
        app,
        storage_backend="redis",
        redis_url="redis://test",
        limit=4,
        window_seconds=60,
    )
    middleware._check_limit = AsyncMock(side_effect=RuntimeError("redis offline"))
    fallback_check = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=1, retry_after=0)
    )
    monkeypatch.setattr(
        "app.core.ratelimit.middleware.MemorySlidingWindowStrategy.check",
        fallback_check,
    )

    await middleware(_http_scope(), AsyncMock(), AsyncMock())

    fallback_check.assert_awaited_once()
    app.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_blocked_response_includes_rate_limit_headers():
    middleware = RateLimitMiddleware(
        AsyncMock(), storage_backend="memory", limit=3, window_seconds=60
    )
    middleware._check_limit = AsyncMock(
        return_value=RateLimitInfo(allowed=False, remaining=0, retry_after=-5)
    )
    sent: list[dict[str, object]] = []
    send = AsyncMock(side_effect=sent.append)

    await middleware(_http_scope(), AsyncMock(), send)

    headers = dict(sent[0]["headers"])
    assert headers[b"Retry-After"] == b"0"
    assert headers[b"X-RateLimit-Limit"] == b"3"
    assert headers[b"X-RateLimit-Remaining"] == b"0"
    assert b"X-RateLimit-Reset" in headers


@pytest.mark.asyncio
async def test_middleware_send_wrapper_adds_missing_headers_and_passes_body():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RateLimitMiddleware(
        app, storage_backend="memory", limit=5, window_seconds=60
    )
    middleware._check_limit = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=4, retry_after=0)
    )
    sent: list[dict[str, object]] = []
    send = AsyncMock(side_effect=sent.append)

    await middleware(_http_scope(), AsyncMock(), send)

    start = sent[0]
    assert dict(start["headers"]) == {
        b"x-ratelimit-limit": b"5",
        b"x-ratelimit-remaining": b"4",
    }
    assert sent[1] == {"type": "http.response.body", "body": b"ok"}


def test_middleware_endpoint_limits_and_hashed_identifiers():
    middleware = RateLimitMiddleware(
        AsyncMock(),
        storage_backend="memory",
        limit=10,
        window_seconds=60,
        endpoint_limits=(EndpointRateLimit("/auth", 2, 30),),
    )
    assert middleware._get_limits_for_path("/auth/login") == (2, 30, "/auth")
    assert middleware._get_limits_for_path("/public") == (10, 60, "default")

    token = "secret-token"
    token_request = Request(
        _http_scope(headers=[(b"authorization", f"Bearer {token}".encode())])
    )
    token_identifier = middleware._build_identifier(token_request)
    assert token_identifier == f"token:{hashlib.sha256(token.encode()).hexdigest()}"
    assert token not in token_identifier

    cookie = "cookie-token"
    cookie_request = Request(
        _http_scope(headers=[(b"cookie", f"access_token_v2={cookie}".encode())])
    )
    assert middleware._build_identifier(cookie_request) == (
        f"cookie:{hashlib.sha256(cookie.encode()).hexdigest()}"
    )
