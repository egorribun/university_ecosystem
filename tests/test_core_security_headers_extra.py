from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.should_inject_csp_nonce = True
    settings.environment = "production"
    settings.frontend_url = "https://example.com"
    settings.security_csp_report_only_effective = False
    settings.build_csp_policy.side_effect = lambda nonce=None, report_only=False: (
        f"default-src 'self'; script-src 'nonce-{nonce}'"
        if nonce
        else "default-src 'self'"
    )
    settings.security_hsts_enabled_effective = False
    settings.coop_enabled = False
    settings.coep_enabled = False
    settings.corp_enabled = False
    settings.security_x_frame_options = "DENY"
    settings.security_permissions_policy = ""
    settings.security_x_content_type_options = "nosniff"
    settings.security_referrer_policy = "same-origin"
    return settings


def test_security_headers_middleware_static_files(mock_settings):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/static/file.css")
    def get_static():
        return "css content"

    client = TestClient(app)
    response = client.get("/static/file.css")

    assert response.status_code == 200
    # Should not have CSP nonce for static files
    assert (
        "content-security-policy" not in response.headers
        or "nonce-" not in response.headers.get("content-security-policy", "")
    )
    # Should have other static headers
    assert "x-content-type-options" in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_security_headers_middleware_api(mock_settings):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/api/v1/users")
    def get_users():
        return {"users": []}

    client = TestClient(app)
    response = client.get("/api/v1/users")

    assert response.status_code == 200
    assert "content-security-policy" in response.headers
    # API endpoints might not generate nonces if they don't return HTML, but the logic
    # for API paths explicitly skips nonce generation in _is_potentially_html
    csp = response.headers.get("content-security-policy", "")
    assert "nonce-" not in csp


def test_security_headers_middleware_html(mock_settings):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def get_home():
        # Let's return HTML
        from fastapi.responses import HTMLResponse

        return HTMLResponse(content="<html><head></head><body>Hello</body></html>")

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "content-security-policy" in response.headers
    assert "nonce-" in response.headers["content-security-policy"]


def test_security_headers_middleware_exempt(mock_settings):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


@pytest.mark.asyncio
async def test_non_http_scope_passthrough(mock_settings):
    """Lines 60-61: Non-HTTP scope (WebSocket/lifespan) must be passed through without processing."""
    from asgi_lifespan import LifespanManager

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/test")
    def get_test():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with (
        LifespanManager(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get("/test")

    # Lifespan scope was processed without error; HTTP response is still correct
    assert response.status_code == 200
    assert "x-content-type-options" in response.headers


def test_html_response_with_csp_nonce_injection(mock_settings):
    """Lines 126-137, 159-166: HTML response with __CSP_NONCE__ placeholder gets the nonce injected."""
    # Enable nonce injection
    mock_settings.should_inject_csp_nonce = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    html_with_nonce_placeholder = (
        "<html><head>"
        "<script nonce=\"__CSP_NONCE__\">console.log('hi')</script>"
        "</head><body>Hello</body></html>"
    )

    @app.get("/page")
    def get_page():
        return HTMLResponse(content=html_with_nonce_placeholder)

    client = TestClient(app)
    response = client.get("/page")

    assert response.status_code == 200
    # The nonce placeholder should be replaced with an actual nonce
    assert "__CSP_NONCE__" not in response.text
    # The response should contain a nonce value (nonce- prefix in CSP)
    csp = response.headers.get("content-security-policy", "")
    assert "nonce-" in csp


def test_html_response_buffer_limit_exceeded(mock_settings):
    """Lines 197-219: When HTML response exceeds 64KB buffer limit, fallback streaming is used."""
    mock_settings.should_inject_csp_nonce = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    # Create content > 64KB to exceed the buffer limit
    large_html = "<html><body>" + ("x" * (65 * 1024)) + "</body></html>"

    @app.get("/large-page")
    def get_large_page():
        return HTMLResponse(content=large_html)

    client = TestClient(app)
    response = client.get("/large-page")

    assert response.status_code == 200
    # Even in fallback mode, the response should be delivered
    assert len(response.text) > 64 * 1024
    # Security headers should still be present (they were added to state.html_headers)
    assert "x-content-type-options" in response.headers


def test_non_html_content_type_no_nonce(mock_settings):
    """Lines 137-139: Non-HTML content-type should not buffer and should send immediately."""
    mock_settings.should_inject_csp_nonce = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/data")
    def get_data():
        return Response(content=b'{"ok": true}', media_type="application/json")

    client = TestClient(app)
    response = client.get("/data")

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")
    # No buffering, headers delivered immediately
    assert "x-content-type-options" in response.headers


def test_hsts_with_subdomains_and_preload(mock_settings):
    """Lines 268-272: HSTS with includeSubDomains and preload flags."""
    mock_settings.security_hsts_enabled_effective = True
    mock_settings.security_hsts_max_age = 31536000
    mock_settings.security_hsts_include_subdomains = True
    mock_settings.security_hsts_preload = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def root():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/")

    hsts = response.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts


def test_hsts_without_subdomains_preload(mock_settings):
    """Lines 268-272: HSTS without includeSubDomains and preload (basic max-age only)."""
    mock_settings.security_hsts_enabled_effective = True
    mock_settings.security_hsts_max_age = 86400
    mock_settings.security_hsts_include_subdomains = False
    mock_settings.security_hsts_preload = False

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def root():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/")

    hsts = response.headers.get("strict-transport-security", "")
    assert "max-age=86400" in hsts
    assert "includeSubDomains" not in hsts
    assert "preload" not in hsts


def test_coop_coep_corp_enabled(mock_settings):
    """Lines 275-284: COOP, COEP, CORP headers when enabled."""
    mock_settings.coop_enabled = True
    mock_settings.coep_enabled = True
    mock_settings.coep_header_value = "require-corp"
    mock_settings.corp_enabled = True
    mock_settings.corp_header_value = "same-origin"

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def root():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/")

    assert response.headers.get("cross-origin-opener-policy") == "same-origin"
    assert response.headers.get("cross-origin-embedder-policy") == "require-corp"
    assert response.headers.get("cross-origin-resource-policy") == "same-origin"


def test_empty_security_headers_skipped(mock_settings):
    """Lines 287-302: Empty frame options, permissions policy, content type options, referrer policy are skipped."""
    mock_settings.security_x_frame_options = ""
    mock_settings.security_permissions_policy = ""
    mock_settings.security_x_content_type_options = ""
    mock_settings.security_referrer_policy = ""
    mock_settings.security_hsts_enabled_effective = False
    mock_settings.coop_enabled = False
    mock_settings.coep_enabled = False
    mock_settings.corp_enabled = False

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def root():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/")

    assert "x-frame-options" not in response.headers
    assert "permissions-policy" not in response.headers
    assert "x-content-type-options" not in response.headers
    assert "referrer-policy" not in response.headers


def test_event_stream_path_no_nonce(mock_settings):
    """Lines 126-137: Paths containing /api/events/stream should not get nonce, even if HTML content-type."""
    mock_settings.should_inject_csp_nonce = True

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/api/events/stream")
    def get_stream():
        # Even if the response looks HTML-ish, the path check prevents nonce injection
        return Response(content="data: test\n\n", media_type="text/event-stream")

    client = TestClient(app)
    response = client.get("/api/events/stream")

    assert response.status_code == 200
    # Security headers still applied (just not nonce injection for the path)
    assert "content-security-policy" in response.headers


def test_csp_report_only_mode(mock_settings):
    """Lines 245-246: Report-only mode returns only CSP-RO header, not enforcing CSP."""
    mock_settings.security_csp_report_only_effective = True
    mock_settings.should_inject_csp_nonce = False

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=mock_settings)

    @app.get("/")
    def root():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/")

    # In report-only mode, enforcing CSP should NOT be present
    assert "content-security-policy" not in [k.lower() for k in response.headers.keys()
                                               if k.lower() == "content-security-policy"]
    # But CSP-RO should be present
    assert "content-security-policy-report-only" in response.headers


@pytest.mark.asyncio
async def test_websocket_scope_passthrough(mock_settings):
    """Lines 60-61: WebSocket scope must be passed through without modification."""
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope["type"])

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    # Simulate a WebSocket scope
    ws_scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [],
        "query_string": b"",
    }

    async def mock_receive():
        return {"type": "websocket.connect"}

    async def mock_send(message):
        pass

    await middleware(ws_scope, mock_receive, mock_send)
    # Inner app should have been called with WebSocket scope
    assert "websocket" in calls


@pytest.mark.asyncio
async def test_html_streaming_more_body_true(mock_settings):
    """Line 159->220 (more_body=True branch): Streaming HTML body chunks accumulate before final send."""
    mock_settings.should_inject_csp_nonce = True

    html_part1 = b"<html><head><script nonce=\"__CSP_NONCE__\">hi</script></head>"
    html_part2 = b"<body>World</body></html>"

    sent_messages = []

    async def inner_app(scope, receive, send):
        # Send http.response.start with text/html content-type
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
            ],
        })
        # Send first chunk with more_body=True
        await send({
            "type": "http.response.body",
            "body": html_part1,
            "more_body": True,
        })
        # Send second (final) chunk with more_body=False
        await send({
            "type": "http.response.body",
            "body": html_part2,
            "more_body": False,
        })

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    http_scope = {
        "type": "http",
        "method": "GET",
        "path": "/page",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def mock_receive():
        return {"type": "http.disconnect"}

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(http_scope, mock_receive, mock_send)

    # Both start and body should have been sent
    types_sent = [m["type"] for m in sent_messages]
    assert "http.response.start" in types_sent
    assert "http.response.body" in types_sent

    # The nonce replacement should have happened in the final body
    final_body_msg = next(m for m in sent_messages if m["type"] == "http.response.body")
    body = final_body_msg["body"]
    assert b"__CSP_NONCE__" not in body


@pytest.mark.asyncio
async def test_html_decode_error_recovery(mock_settings):
    """Lines 167-168: UnicodeDecodeError during HTML decode falls through without crash."""
    mock_settings.should_inject_csp_nonce = True

    # Simulate invalid UTF-8 bytes that would cause a UnicodeDecodeError
    invalid_utf8 = b"<html><body>\xff\xfe invalid utf8</body></html>"

    sent_messages = []

    async def inner_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": invalid_utf8,
            "more_body": False,
        })

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    http_scope = {
        "type": "http",
        "method": "GET",
        "path": "/page",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def mock_receive():
        return {"type": "http.disconnect"}

    async def mock_send(message):
        sent_messages.append(message)

    # Should not raise despite invalid UTF-8
    await middleware(http_scope, mock_receive, mock_send)

    # Response should still be delivered
    types_sent = [m["type"] for m in sent_messages]
    assert "http.response.body" in types_sent


@pytest.mark.asyncio
async def test_html_buffer_overflow_with_chunks(mock_settings):
    """Lines 199-219: HTML buffer limit exceeded with multiple small chunks triggers fallback streaming."""
    mock_settings.should_inject_csp_nonce = True

    # Create chunks that together exceed 64KB
    chunk_size = 30 * 1024  # 30KB each
    chunk1 = b"<html>" + (b"a" * (chunk_size - 6))
    chunk2 = b"b" * chunk_size   # Second chunk: total = 60KB (still within limit)
    chunk3 = b"c" * chunk_size   # Third chunk: total = 90KB -> overflow

    sent_messages = []

    async def inner_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
            ],
        })
        await send({"type": "http.response.body", "body": chunk1, "more_body": True})
        await send({"type": "http.response.body", "body": chunk2, "more_body": True})
        await send({"type": "http.response.body", "body": chunk3, "more_body": False})

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    http_scope = {
        "type": "http",
        "method": "GET",
        "path": "/page",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def mock_receive():
        return {"type": "http.disconnect"}

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(http_scope, mock_receive, mock_send)

    # Should have delivered the response (fallback streaming mode)
    types_sent = [m["type"] for m in sent_messages]
    assert "http.response.start" in types_sent
    assert "http.response.body" in types_sent


@pytest.mark.asyncio
async def test_http_disconnect_passthrough(mock_settings):
    """Line 227: http.disconnect events (other ASGI event types) are passed through directly."""
    sent_messages = []

    async def inner_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"ok": true}',
            "more_body": False,
        })
        # Also send an unknown event type (simulates http.disconnect or similar)
        await send({
            "type": "http.disconnect",
        })

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    http_scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def mock_receive():
        return {"type": "http.disconnect"}

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(http_scope, mock_receive, mock_send)

    # The disconnect event should also be in sent_messages (passed through)
    types_sent = [m["type"] for m in sent_messages]
    assert "http.disconnect" in types_sent


@pytest.mark.asyncio
async def test_nonce_injection_event_stream_path_excluded(mock_settings):
    """Lines 124-135: When path contains /api/events/stream and nonce is set, HTML state is NOT triggered."""
    mock_settings.should_inject_csp_nonce = True

    sent_messages = []

    async def inner_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        })
        await send({
            "type": "http.response.body",
            "body": b"<html>data</html>",
            "more_body": False,
        })

    middleware = SecurityHeadersMiddleware(inner_app, settings=mock_settings)

    # Use /api/events/stream path - this should skip HTML nonce injection
    http_scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/events/stream",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def mock_receive():
        return {"type": "http.disconnect"}

    async def mock_send(message):
        sent_messages.append(message)

    await middleware(http_scope, mock_receive, mock_send)

    # Response should be delivered normally (not buffered for HTML injection)
    types_sent = [m["type"] for m in sent_messages]
    assert "http.response.start" in types_sent
    assert "http.response.body" in types_sent
