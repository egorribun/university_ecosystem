"""Tests for exception handlers and request-ID middleware.

Handlers tested with a duck-typed SimpleNamespace request (resolve_locale +
str(request.url) only need .url/.headers/.query_params). RequestIDMiddleware
tested as a raw ASGI callable with async receive/send mocks.

asyncio_mode = "auto" (pyproject) — async test fns need no decorator.
"""

from __future__ import annotations

import json
import types
import uuid
from typing import Any

import pytest
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    DomainException,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.exceptions.handlers import (
    _loc_to_pointer,
    domain_exception_handler,
    http_exception_handler,
)
from app.core.middleware.request_id import (
    _REQUEST_ID_SAFE_CHARS,
    RequestIDMiddleware,
    request_id_ctx,
)


def _make_request(
    url: str = "http://testserver/api/v1/x", locale: str | None = None
) -> Any:
    """Duck-typed request: handlers only call resolve_locale(request=...) and
    str(request.url). resolve_locale reads .query_params/.headers via getattr."""
    query_params = None
    if locale is not None:
        query_params = types.SimpleNamespace(
            get=lambda key, _loc=locale: _loc if key == "lang" else None
        )
    return types.SimpleNamespace(url=url, headers=None, query_params=query_params)


# ── _loc_to_pointer (RFC 6901) ────────────────────────────────────────────────
def test_loc_to_pointer_empty() -> None:
    assert _loc_to_pointer(()) == ""


def test_loc_to_pointer_basic_path() -> None:
    assert _loc_to_pointer(("body", "user", "email")) == "/body/user/email"


def test_loc_to_pointer_int_segment() -> None:
    assert _loc_to_pointer(("body", "items", 0, "name")) == "/body/items/0/name"


def test_loc_to_pointer_escapes_tilde_and_slash() -> None:
    assert _loc_to_pointer(("a/b~c",)) == "/a~1b~0c"
    # tilde escaped before slash: literal "~1" -> "~01" not "~11"
    assert _loc_to_pointer(("~1",)) == "/~01"


# ── domain_exception_handler ──────────────────────────────────────────────────
async def test_domain_handler_entity_not_found_404() -> None:
    exc = EntityNotFound("User", "abc-123")
    resp = await domain_exception_handler(_make_request(), exc)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.media_type == "application/problem+json"
    body = json.loads(resp.body)
    assert body["type"] == "https://api.university.edu/probs/not-found"
    assert body["status"] == 404
    assert body["instance"] == "http://testserver/api/v1/x"
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]
    assert "trace_id" in body


async def test_domain_handler_already_exists_409() -> None:
    exc = EntityAlreadyExists("News", 42)
    resp = await domain_exception_handler(_make_request(), exc)
    assert resp.status_code == status.HTTP_409_CONFLICT
    body = json.loads(resp.body)
    assert body["type"] == "https://api.university.edu/probs/conflict"
    # errors.already_exists en = "Record already exists: {identifier}"
    assert body["detail"] == "Record already exists: 42"


async def test_domain_handler_permission_denied_403() -> None:
    exc = PermissionDenied()
    resp = await domain_exception_handler(_make_request(), exc)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    body = json.loads(resp.body)
    assert body["type"] == "https://api.university.edu/probs/forbidden"
    assert isinstance(body["title"], str) and body["title"]


async def test_domain_handler_business_rule_400() -> None:
    exc = BusinessRuleViolation("Capacity exceeded")
    resp = await domain_exception_handler(_make_request(), exc)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    body = json.loads(resp.body)
    assert body["type"] == "https://api.university.edu/probs/business-rule"
    assert body["detail"] == "Capacity exceeded"  # exc.message verbatim


async def test_domain_handler_generic_fallback_400() -> None:
    exc = DomainException("raw domain failure")
    resp = await domain_exception_handler(_make_request(), exc)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    body = json.loads(resp.body)
    assert body["type"] == "about:blank"
    assert body["detail"] == "raw domain failure"  # str(exc)


async def test_domain_handler_localizes_ru() -> None:
    # resolve_locale reads request.query_params.get("lang") -> "ru"
    exc_en = EntityNotFound("User", 1)
    resp_en = await domain_exception_handler(_make_request(), exc_en)
    title_en = json.loads(resp_en.body)["title"]

    exc_ru = EntityNotFound("User", 1)
    resp_ru = await domain_exception_handler(_make_request(locale="ru"), exc_ru)
    body_ru = json.loads(resp_ru.body)
    # RU localization differs from EN (proves the query-param locale path ran)
    assert body_ru["title"] != title_en
    assert isinstance(body_ru["title"], str) and body_ru["title"]


# ── http_exception_handler ────────────────────────────────────────────────────
async def test_http_handler_404() -> None:
    exc = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="missing")
    resp = await http_exception_handler(_make_request(), exc)
    assert resp.status_code == 404
    assert resp.media_type == "application/problem+json"
    body = json.loads(resp.body)
    assert body["type"] == "about:blank"
    assert body["detail"] == "missing"  # exc.detail
    assert body["instance"] == "http://testserver/api/v1/x"
    assert isinstance(body["title"], str) and body["title"]


async def test_http_handler_unmapped_status() -> None:
    exc = HTTPException(status_code=418, detail="teapot")
    resp = await http_exception_handler(_make_request(), exc)
    assert resp.status_code == 418
    body = json.loads(resp.body)
    assert isinstance(body["title"], str) and body["title"]
    assert body["detail"] == "teapot"


async def test_http_handler_passes_headers() -> None:
    exc = HTTPException(
        status_code=401, detail="auth", headers={"WWW-Authenticate": "Bearer"}
    )
    resp = await http_exception_handler(_make_request(), exc)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    body = json.loads(resp.body)
    assert isinstance(body["title"], str) and body["title"]


async def test_asgi_json_problem_emits_problem_json() -> None:
    from app.core.exceptions.handlers import asgi_json_problem

    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    await asgi_json_problem(
        send,
        status_code=403,
        title_key="titles.forbidden",
        detail_text="nope",
        locale="en",
        instance="http://x/y",
        headers={"X-Custom": "v"},
    )
    start = sent[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 403
    # ASGI header keys are encoded preserving input case — lookup case-insensitively
    hdrs = {k.lower(): v for k, v in start["headers"]}
    assert hdrs[b"content-type"] == b"application/problem+json"
    assert hdrs[b"x-custom"] == b"v"
    body = json.loads(sent[1]["body"])
    assert body["detail"] == "nope"  # detail_text wins
    assert body["status"] == 403
    assert isinstance(body["title"], str) and body["title"]


# ── RequestIDMiddleware ───────────────────────────────────────────────────────
def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {"type": "http", "method": "GET", "path": "/", "headers": headers or []}


async def _noop_receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


class _CapturingApp:
    """Inner ASGI app: emits http.response.start (so the wrapped send appends
    x-request-id) and records the request_id_ctx value visible to handlers."""

    def __init__(self) -> None:
        self.seen_scope: dict[str, Any] | None = None
        self.ctx_during_call: str | None = None

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        self.seen_scope = scope
        self.ctx_during_call = request_id_ctx.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def test_request_id_non_http_passthrough() -> None:
    inner = _CapturingApp()
    mw = RequestIDMiddleware(inner)
    sent: list[dict] = []

    async def send(m: dict) -> None:
        sent.append(m)

    scope = {"type": "lifespan"}
    await mw(scope, _noop_receive, send)
    assert inner.seen_scope == scope  # delegated untouched


async def test_request_id_generated_when_absent() -> None:
    inner = _CapturingApp()
    mw = RequestIDMiddleware(inner)
    sent: list[dict] = []

    async def send(m: dict) -> None:
        sent.append(m)

    scope = _http_scope(headers=[])
    await mw(scope, _noop_receive, send)
    rid = scope["state"]["request_id"]
    assert rid and uuid.UUID(rid)  # generated UUID4 (parses)
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert (b"x-request-id", rid.encode("ascii")) in start["headers"]
    assert inner.ctx_during_call == rid  # ctx var live during handler
    assert request_id_ctx.get() == ""  # reset in finally


async def test_request_id_incoming_header_sanitized() -> None:
    inner = _CapturingApp()
    mw = RequestIDMiddleware(inner)
    sent: list[dict] = []

    async def send(m: dict) -> None:
        sent.append(m)

    raw = "abc-123_DEF\r\nInjected: x  /<>;"  # CRLF + spaces + meta chars
    scope = _http_scope(headers=[(b"x-request-id", raw.encode("latin-1"))])
    await mw(scope, _noop_receive, send)
    rid = scope["state"]["request_id"]
    assert rid == "abc-123_DEFInjectedx"  # only alnum + - + _ survive
    assert all(c in _REQUEST_ID_SAFE_CHARS for c in rid)


async def test_request_id_truncated_to_64() -> None:
    inner = _CapturingApp()
    mw = RequestIDMiddleware(inner)
    sent: list[dict] = []

    async def send(m: dict) -> None:
        sent.append(m)

    raw = "a" * 200
    scope = _http_scope(headers=[(b"x-request-id", raw.encode("ascii"))])
    await mw(scope, _noop_receive, send)
    assert scope["state"]["request_id"] == "a" * 64


async def test_request_id_context_reset_on_inner_exception() -> None:
    class _Boom:
        async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
            raise RuntimeError("boom")

    mw = RequestIDMiddleware(_Boom())

    async def send(m: dict) -> None:
        pass

    scope = _http_scope(headers=[(b"x-request-id", b"fixed-id")])
    with pytest.raises(RuntimeError):
        await mw(scope, _noop_receive, send)
    assert request_id_ctx.get() == ""  # finally still ran
