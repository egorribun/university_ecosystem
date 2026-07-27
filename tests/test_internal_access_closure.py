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
