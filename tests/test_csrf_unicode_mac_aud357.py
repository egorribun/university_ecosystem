from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

import app.core.csrf as csrf_module
from app.core.csrf import (
    _ANON_NONCE_COOKIE_NAME,
    _ROTATE_CSRF_KEY,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRFMiddleware,
    _build_signed_token,
    _verify_signed_token,
)

_TEST_SECRET = b"aud357-test-secret-with-at-least-32-bytes"


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/mut")
    async def mutate() -> dict[str, str]:
        return {"ok": "yes"}

    app.add_middleware(CSRFMiddleware, csrf_hmac_secret=_TEST_SECRET.decode("ascii"))
    return app


class _RequestCapture:
    def __init__(self, app: Any) -> None:
        self._app = app
        self.values: list[tuple[str | None, str | None]] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        self.values.append(
            (
                request.cookies.get(CSRF_COOKIE_NAME),
                request.headers.get(CSRF_HEADER_NAME),
            )
        )
        await self._app(scope, receive, send)


@pytest.mark.parametrize(
    ("cookie_token", "header_token"),
    [
        ("nonce.\u00e9", "nonce.\u00e9"),
        ("nonce.ascii", "nonce.\u00e9"),
        ("nonce.\u00e9", "nonce.ascii"),
    ],
    ids=("both-non-ascii", "header-non-ascii", "cookie-non-ascii"),
)
@pytest.mark.asyncio
async def test_non_ascii_double_submit_values_return_403(
    cookie_token: str,
    header_token: str,
) -> None:
    app = _make_app()
    capture = _RequestCapture(app)
    transport = httpx.ASGITransport(app=capture, raise_app_exceptions=False)
    raw_headers = [
        (b"cookie", b"csrf_token=" + cookie_token.encode("latin-1")),
        (b"x-csrf-token", header_token.encode("latin-1")),
    ]

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post("/mut", headers=raw_headers)

    assert capture.values == [(cookie_token, header_token)]
    parsed_cookie, parsed_header = capture.values[0]
    assert type(parsed_cookie) is str
    assert type(parsed_header) is str
    assert not parsed_cookie.isascii() or not parsed_header.isascii()
    assert response.status_code == 403


def test_signed_token_verifier_rejects_non_ascii_mac() -> None:
    malformed = f"nonce.{'a' * 63}\u00e9"

    assert _verify_signed_token(malformed, "session-A", _TEST_SECRET) is False


def test_signed_token_verifier_keeps_ascii_malformed_and_valid_controls() -> None:
    malformed_ascii = f"nonce.{'g' * 64}"
    valid_ascii = _build_signed_token("session-A", _TEST_SECRET)

    assert _verify_signed_token(malformed_ascii, "session-A", _TEST_SECRET) is False
    assert _verify_signed_token(valid_ascii, "session-A", _TEST_SECRET) is True


@pytest.mark.asyncio
async def test_valid_ascii_double_submit_uses_ascii_constant_time_comparisons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app()
    nonce = "a" * 32
    token = _build_signed_token(f"anon:{nonce}", _TEST_SECRET)
    original_compare_digest = csrf_module.secrets.compare_digest
    comparisons: list[tuple[str, bool, str, bool]] = []

    def record_compare(left: str, right: str) -> bool:
        comparisons.append(
            (type(left).__name__, left.isascii(), type(right).__name__, right.isascii())
        )
        return original_compare_digest(left, right)

    private_secrets = SimpleNamespace(
        compare_digest=record_compare,
        token_hex=csrf_module.secrets.token_hex,
        token_urlsafe=csrf_module.secrets.token_urlsafe,
    )
    monkeypatch.setattr(csrf_module, "secrets", private_secrets)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        client.cookies.set(CSRF_COOKIE_NAME, token)
        client.cookies.set(_ANON_NONCE_COOKIE_NAME, nonce)
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: token})

    assert response.status_code == 200
    assert comparisons == [
        ("str", True, "str", True),
        ("str", True, "str", True),
    ]


@pytest.mark.asyncio
async def test_rotation_does_not_refresh_malformed_anonymous_nonce_cookie() -> None:
    async def inner_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = CSRFMiddleware(
        inner_app, csrf_hmac_secret=_TEST_SECRET.decode("ascii")
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/mut",
        "raw_path": b"/mut",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (
                b"cookie",
                b"csrf_token=existing-token; _csrf_anon_nonce=invalid",
            )
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {"session_id": "session-A", _ROTATE_CSRF_KEY: True},
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(scope, receive, send)

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 200
    set_cookies = [
        value
        for name, value in response_start["headers"]
        if name.lower() == b"set-cookie"
    ]
    assert len(set_cookies) == 1
    assert b"csrf_token=" in set_cookies[0]
    assert b"_csrf_anon_nonce=" not in set_cookies[0]
