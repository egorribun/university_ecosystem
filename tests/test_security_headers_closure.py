"""Branch closure tests for ASGI security-header response handling."""

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware


def _settings():
    settings = MagicMock(spec=Settings)
    settings.should_inject_csp_nonce = True
    settings.security_csp_report_only_effective = False
    settings.build_csp_policy.side_effect = lambda nonce=None, report_only=False: (
        f"default-src 'self'; script-src 'nonce-{nonce}'"
    )
    settings.security_hsts_enabled_effective = False
    settings.coop_enabled = False
    settings.coep_enabled = False
    settings.corp_enabled = False
    settings.security_x_frame_options = ""
    settings.security_permissions_policy = ""
    settings.security_x_content_type_options = "nosniff"
    settings.security_referrer_policy = ""
    return settings


async def _receive():
    return {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_event_stream_marker_in_non_api_path_skips_html_buffering():
    sent = []

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html; charset=utf-8")],
            }
        )
        await send(
            {"type": "http.response.body", "body": b"stream", "more_body": False}
        )

    middleware = SecurityHeadersMiddleware(app, settings=_settings())
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/events/api/events/stream",
        "query_string": b"",
        "headers": [],
    }

    async def send(message):
        sent.append(message)

    await middleware(scope, _receive, send)

    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]


@pytest.mark.asyncio
async def test_html_overflow_after_fallback_sends_later_chunks_directly():
    sent = []
    chunks = [
        b"<html>" + b"a" * (30 * 1024 - 6),
        b"b" * (30 * 1024),
        b"c" * (30 * 1024),
        b"tail",
    ]

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html")],
            }
        )
        for index, chunk in enumerate(chunks):
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": index < len(chunks) - 1,
                }
            )

    middleware = SecurityHeadersMiddleware(app, settings=_settings())
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/large",
        "query_string": b"",
        "headers": [],
    }

    async def send(message):
        sent.append(message)

    await middleware(scope, _receive, send)

    body_messages = [
        message for message in sent if message["type"] == "http.response.body"
    ]
    assert body_messages[-1]["body"] == b"tail"
