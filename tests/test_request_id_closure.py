"""Closure tests for optional structlog integration in request ID middleware."""

import builtins
import runpy
from unittest.mock import patch

import pytest

import app.core.middleware.request_id as request_id_module
from app.core.middleware.request_id import RequestIDMiddleware


@pytest.mark.asyncio
async def test_request_id_middleware_works_without_structlog_contextvars():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "state": {},
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})

    with patch.object(request_id_module, "clear_contextvars", None):
        await RequestIDMiddleware(inner)(scope, receive, send)

    assert any((key == b"x-request-id" and value) for key, value in sent[0]["headers"])


@pytest.mark.asyncio
async def test_request_id_middleware_forwards_non_http_scopes_unchanged():
    called = []

    async def inner(scope, receive, send):
        called.append((scope, receive, send))

    scope = {"type": "websocket"}
    receive = object()
    send = object()

    await RequestIDMiddleware(inner)(scope, receive, send)

    assert called == [(scope, receive, send)]


@pytest.mark.asyncio
async def test_request_id_middleware_sanitizes_truncates_and_clears_context():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"x-request-id", b"a!" + b"b" * 80)],
        "state": {},
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    with patch.object(request_id_module, "clear_contextvars") as clear:
        await RequestIDMiddleware(inner)(scope, receive, send)

    request_id = scope["state"]["request_id"]
    assert request_id == "ab" + "b" * 62
    assert (b"x-request-id", request_id.encode("ascii")) in sent[0]["headers"]
    assert sent[1]["type"] == "http.response.body"
    clear.assert_called_once_with()


def test_request_id_module_handles_missing_structlog_contextvars_import():
    real_import = builtins.__import__

    def import_without_structlog_contextvars(name, *args, **kwargs):
        if name == "structlog.contextvars":
            raise ImportError("optional structlog contextvars unavailable")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=import_without_structlog_contextvars):
        namespace = runpy.run_path(
            request_id_module.__file__,
            run_name="app.core.middleware.request_id_without_structlog",
        )

    assert namespace["clear_contextvars"] is None
