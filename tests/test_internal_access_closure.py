"""Closure tests for ASGI internal-access edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.internal_access import InternalAccessMiddleware


def _scope(*, scope_type="http", path="/internal/test", headers=None):
    return {
        "type": scope_type,
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 1),
        "method": "GET",
    }


@pytest.mark.asyncio
async def test_non_http_scope_passes_through():
    app = AsyncMock()
    middleware = InternalAccessMiddleware(app, internal_prefixes=["/internal"])
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(_scope(scope_type="lifespan"), receive, send)

    app.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_internal_path_passes_through_without_authentication():
    app = AsyncMock()
    middleware = InternalAccessMiddleware(app, internal_prefixes=["/internal"])

    await middleware(_scope(path="/public"), AsyncMock(), AsyncMock())

    app.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_header_allows_request_and_injects_vary_header():
    sent = []

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    middleware = InternalAccessMiddleware(
        app,
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=["/internal"],
    )
    await middleware(
        _scope(headers=[(b"x-internal-token", b"secret")]),
        AsyncMock(),
        send,
    )

    assert sent[0]["headers"] == [(b"vary", b"X-Internal-Token")]
    assert sent[1]["type"] == "http.response.body"


@pytest.mark.asyncio
async def test_allowed_ip_passes_request_without_header_token():
    app = AsyncMock()
    middleware = InternalAccessMiddleware(
        app, allowed_ips=["127.0.0.1"], internal_prefixes=["/internal"]
    )

    await middleware(_scope(), AsyncMock(), AsyncMock())

    app.assert_awaited_once()


@pytest.mark.asyncio
async def test_denied_internal_request_returns_forbidden_json():
    sent = []

    async def send(message):
        sent.append(message)

    middleware = InternalAccessMiddleware(AsyncMock(), internal_prefixes=["/internal"])
    await middleware(_scope(), AsyncMock(), send)

    assert sent[0]["status"] == 403
    assert sent[1]["body"] == b'{"detail":"Internal API access denied"}'


def test_header_decode_failures_are_rejected():
    class InvalidBytes(bytes):
        def decode(self, encoding="utf-8", errors="strict"):
            raise ValueError("invalid header")

    middleware = InternalAccessMiddleware(
        AsyncMock(), header_name="X-Internal", header_token="secret"
    )
    assert (
        middleware._has_valid_header_from_scope({b"x-internal": InvalidBytes(b"x")})
        is False
    )


def test_header_and_ip_helpers_cover_missing_and_valid_values():
    middleware = InternalAccessMiddleware(
        AsyncMock(),
        allowed_ips=[" 127.0.0.1 ", ""],
        header_name="X-Internal",
        header_token="secret",
    )

    assert middleware._is_allowed_ip_from_scope("127.0.0.1") is True
    assert middleware._is_allowed_ip_from_scope("10.0.0.1") is False
    assert middleware._has_valid_header_from_scope({}) is False
    assert middleware._has_valid_header_from_scope({b"x-internal": b"wrong"}) is False
    assert middleware._has_valid_header_from_scope({b"x-internal": b"secret"}) is True
    assert (
        InternalAccessMiddleware(AsyncMock())._is_allowed_ip_from_scope("127.0.0.1")
        is False
    )


@pytest.mark.asyncio
async def test_vary_wrapper_adds_header_and_forwards_non_start_messages():
    send = AsyncMock()
    middleware = InternalAccessMiddleware(AsyncMock(), header_name="X-Internal")
    wrapped = middleware._make_vary_send(send)

    await wrapped({"type": "http.response.body", "body": b"ok"})

    assert send.await_args.args[0]["type"] == "http.response.body"
    assert InternalAccessMiddleware(AsyncMock())._make_vary_send(send) is send


@pytest.mark.asyncio
async def test_vary_wrapper_appends_missing_header_to_existing_vary():
    send = AsyncMock()
    middleware = InternalAccessMiddleware(AsyncMock(), header_name="X-Internal")
    wrapped = middleware._make_vary_send(send)

    await wrapped(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"vary", b"Origin")],
        }
    )

    assert send.await_args.args[0]["headers"] == [(b"vary", b"Origin, X-Internal")]


@pytest.mark.asyncio
async def test_vary_wrapper_keeps_non_vary_headers_and_does_not_duplicate_token():
    app = AsyncMock()
    middleware = InternalAccessMiddleware(
        app,
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=["/internal"],
    )
    send = AsyncMock()
    wrapped = middleware._make_vary_send(send)

    await wrapped(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"vary", b"X-Internal-Token, Origin"),
            ],
        }
    )

    message = send.await_args.args[0]
    assert (b"content-type", b"application/json") in message["headers"]
    assert (b"vary", b"X-Internal-Token, Origin") in message["headers"]
