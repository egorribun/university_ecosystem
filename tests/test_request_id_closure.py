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
