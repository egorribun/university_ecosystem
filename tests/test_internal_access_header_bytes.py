"""Internal token rejection must handle arbitrary HTTP header bytes safely."""

from unittest.mock import AsyncMock

import pytest

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.internal_access import InternalAccessMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize("path", INTERNAL_ROUTE_PREFIXES)
@pytest.mark.parametrize("provided", [b"wrong", b"\x80", b"\xff", b"secret\xe9"])
async def test_non_ascii_or_wrong_internal_token_is_forbidden(path, provided, caplog):
    app = AsyncMock()
    send = AsyncMock()
    middleware = InternalAccessMiddleware(
        app,
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=INTERNAL_ROUTE_PREFIXES,
        allowed_ips=["127.0.0.1"],
        allow_ip_fallback=False,
    )
    scope = {
        "type": "http",
        "path": path,
        "method": "GET",
        "headers": [(b"x-internal-token", provided)],
        "client": ("127.0.0.1", 1),
    }

    await middleware(scope, AsyncMock(), send)

    app.assert_not_awaited()
    messages = [call.args[0] for call in send.await_args_list]
    assert messages[0]["status"] == 403
    assert messages[1]["body"] == b'{"detail":"Internal API access denied"}'
    assert "secret" not in caplog.text
    assert provided.decode("latin-1") not in caplog.text


@pytest.mark.parametrize("configured", ["secr\u00e9t", "\u041f\u0430\u0440\u043e\u043b\u044c"])
@pytest.mark.parametrize("provided", [b"secret", b"secr\xe9t", b"\xff"])
def test_non_ascii_configured_token_never_authenticates(configured, provided):
    middleware = InternalAccessMiddleware(
        AsyncMock(), header_name="X-Internal-Token", header_token=configured
    )

    assert not middleware._has_valid_header_from_scope({b"x-internal-token": provided})


@pytest.mark.asyncio
async def test_ascii_token_still_reaches_handler_with_vary():
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    middleware = InternalAccessMiddleware(
        app,
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=INTERNAL_ROUTE_PREFIXES,
    )
    await middleware(
        {
            "type": "http",
            "path": INTERNAL_ROUTE_PREFIXES[0],
            "headers": [(b"x-internal-token", b"secret")],
            "client": ("127.0.0.1", 1),
        },
        AsyncMock(),
        send,
    )

    assert sent[0]["status"] == 200
    assert sent[0]["headers"] == [(b"vary", b"X-Internal-Token")]
    assert sent[1]["body"] == b"ok"


@pytest.mark.asyncio
async def test_non_ascii_token_on_public_path_does_not_add_authentication():
    app = AsyncMock()
    middleware = InternalAccessMiddleware(
        app,
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=INTERNAL_ROUTE_PREFIXES,
    )
    scope = {
        "type": "http",
        "path": "/api/v1/chat/messages",
        "headers": [(b"x-internal-token", b"\xff")],
    }
    receive, send = AsyncMock(), AsyncMock()

    await middleware(scope, receive, send)

    app.assert_awaited_once_with(scope, receive, send)
