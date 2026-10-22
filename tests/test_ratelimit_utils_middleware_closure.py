"""Deterministic unit coverage for ratelimit utility and middleware edges."""

from __future__ import annotations

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
async def test_middleware_head_dynamic_path_remains_rate_limited():
    """HEAD must bypass only public static assets, never dynamic endpoints."""
    app = AsyncMock()
    middleware = RateLimitMiddleware(app, storage_backend="memory")
    middleware._check_limit = AsyncMock(
        return_value=RateLimitInfo(allowed=True, remaining=119, retry_after=0)
    )

    await middleware(
        _http_scope(path="/api/v1/news", method="HEAD"),
        AsyncMock(),
        AsyncMock(),
    )

    middleware._check_limit.assert_awaited_once()
    app.assert_awaited_once()


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
    headers = sent[0]["headers"]
    assert all(name == name.lower() for name, _value in headers)
    assert dict(headers)[b"x-ratelimit-limit"] == b"4"


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

    raw_headers = sent[0]["headers"]
    assert all(name == name.lower() for name, _value in raw_headers)
    headers = dict(raw_headers)
    assert headers[b"retry-after"] == b"0"
    assert headers[b"x-ratelimit-limit"] == b"3"
    assert headers[b"x-ratelimit-remaining"] == b"0"
    assert b"x-ratelimit-reset" in headers


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


def test_middleware_endpoint_limits_and_ip_identifiers():
    middleware = RateLimitMiddleware(
        AsyncMock(),
        storage_backend="memory",
        limit=10,
        window_seconds=60,
        endpoint_limits=(EndpointRateLimit("/auth", 2, 30),),
    )
    assert middleware._get_limits_for_path("/auth/login") == (2, 30, "/auth")
    assert middleware._get_limits_for_path("/public") == (10, 60, "default")

    requests = (
        Request(_http_scope(headers=[(b"authorization", b"Bearer not-a-jwt-one")])),
        Request(_http_scope(headers=[(b"authorization", b"Bearer not-a-jwt-two")])),
        Request(
            _http_scope(headers=[(b"cookie", b"access_token_v2=not-a-jwt-cookie")])
        ),
        Request(_http_scope()),
    )
    assert {middleware._build_identifier(request) for request in requests} == {
        "ip:127.0.0.1"
    }

    other_ip = _http_scope()
    other_ip["client"] = ("198.51.100.7", 5000)
    assert middleware._build_identifier(Request(other_ip)) == "ip:198.51.100.7"


@pytest.mark.asyncio
async def test_rotating_unverified_credentials_cannot_bypass_ip_limit():
    app = AsyncMock()
    middleware = RateLimitMiddleware(
        app,
        storage_backend="memory",
        limit=1,
        window_seconds=60,
        headers_enabled=False,
    )
    scopes = (
        _http_scope(headers=[(b"authorization", b"Bearer not-a-jwt-one")]),
        _http_scope(headers=[(b"authorization", b"Bearer not-a-jwt-two")]),
        _http_scope(headers=[(b"cookie", b"access_token_v2=not-a-jwt-cookie")]),
        _http_scope(),
    )
    responses: list[list[dict[str, object]]] = []
    for scope in scopes:
        messages: list[dict[str, object]] = []
        await middleware(scope, AsyncMock(), AsyncMock(side_effect=messages.append))
        responses.append(messages)

    app.assert_awaited_once()
    assert responses[0] == []
    assert [messages[0]["status"] for messages in responses[1:]] == [429, 429, 429]

    other_ip = _http_scope()
    other_ip["client"] = ("198.51.100.7", 5000)
    await middleware(other_ip, AsyncMock(), AsyncMock())
    assert app.await_count == 2


def test_resolve_client_ip_reads_rfc7239_node_ports_behind_trusted_gateway(
    monkeypatch,
):
    """AUD-164: gateways emit `ip:port` and `[ipv6]:port` node values.

    Dropping those hops made every client behind the gateway share the
    gateway's own rate-limit bucket.
    """
    monkeypatch.setattr(settings, "trusted_proxies_list", ["127.0.0.0/8"])

    with_port = _proxy_request("127.0.0.1", {"X-Forwarded-For": "203.0.113.9:4711"})
    assert resolve_client_ip(with_port) == "203.0.113.9"

    trusted_hop_with_port = _proxy_request(
        "127.0.0.1", {"X-Forwarded-For": "203.0.113.9:4711, 127.0.0.2:80"}
    )
    assert resolve_client_ip(trusted_hop_with_port) == "203.0.113.9"

    forwarded_v4 = _proxy_request(
        "127.0.0.1", {"Forwarded": "for=192.0.2.43:47011;proto=https"}
    )
    assert resolve_client_ip(forwarded_v4) == "192.0.2.43"

    forwarded_v6 = _proxy_request(
        "127.0.0.1", {"Forwarded": 'for="[2001:db8::7]:4711";proto=https'}
    )
    assert resolve_client_ip(forwarded_v6) == "2001:db8::7"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.9", "203.0.113.9"),
        ("203.0.113.9:4711", "203.0.113.9"),
        ('"[2001:db8::7]:4711"', "2001:db8::7"),
        ("[2001:db8::7]", "2001:db8::7"),
        ("2001:db8::7", "2001:db8::7"),
        ("unknown", "unknown"),
        ("", ""),
    ],
)
def test_forwarded_node_host_strips_quotes_brackets_and_ports(raw, expected):
    from app.core.ratelimit.utils import _forwarded_node_host

    assert _forwarded_node_host(raw) == expected
