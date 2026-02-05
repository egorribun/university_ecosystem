import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, Response
from starlette.responses import FileResponse, JSONResponse
from starlette.types import ASGIApp

from app.core.internal_access import InternalAccessMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.timing import RequestTimingMiddleware, ensure_minimum_time


@pytest.mark.asyncio
async def test_ensure_minimum_time():
    start = time.perf_counter()
    # Test shortfall
    await ensure_minimum_time(start, 0.1)
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.1

    # Test no shortfall
    start = time.perf_counter() - 0.2
    await ensure_minimum_time(start, 0.1)
    # Should return immediately


@pytest.mark.asyncio
async def test_request_timing_middleware():
    app = MagicMock(spec=ASGIApp)
    middleware = RequestTimingMiddleware(app)
    request = MagicMock(spec=Request)
    request.url.path = "/test"
    request.method = "GET"

    async def call_next(req):
        return Response(content="ok", status_code=200)

    # Normal request
    response = await middleware.dispatch(request, call_next)
    assert "X-Response-Time" in response.headers

    # Slow request
    async def slow_call_next(req):
        await asyncio.sleep(0.6)
        return Response(content="slow", status_code=200)

    with patch("app.core.timing.logger") as mock_logger:
        response = await middleware.dispatch(request, slow_call_next)
        assert mock_logger.warning.called


@pytest.mark.asyncio
async def test_internal_access_middleware():
    app = MagicMock(spec=ASGIApp)
    middleware = InternalAccessMiddleware(
        app,
        allowed_ips=["127.0.0.1"],
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=["/internal"],
    )

    async def call_next(req):
        return Response(content="ok", status_code=200)

    # Non-internal path
    request = MagicMock(spec=Request)
    request.url.path = "/public"
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200

    # Internal path, allowed IP
    request = MagicMock(spec=Request)
    request.url.path = "/internal/stats"
    request.client.host = "127.0.0.1"
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200

    # Internal path, denied IP, valid header
    request = MagicMock(spec=Request)
    request.url.path = "/internal/stats"
    request.client.host = "192.168.1.1"
    request.headers = {"X-Internal-Token": "secret"}
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert "Vary" in response.headers
    assert "X-Internal-Token" in response.headers["Vary"]

    # Internal path, denied IP, invalid header
    request.headers = {"X-Internal-Token": "wrong"}
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 403

    # Internal path, denied IP, no header
    request.headers = {}
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 403

    # Test _ensure_vary_header with existing Vary
    response = Response(content="ok")
    response.headers["Vary"] = "Accept-Encoding"
    middleware._ensure_vary_header(response)
    assert "X-Internal-Token" in response.headers["Vary"]
    assert "Accept-Encoding" in response.headers["Vary"]


@pytest.mark.asyncio
async def test_security_headers_middleware():
    app = MagicMock(spec=ASGIApp)
    settings = MagicMock()
    settings.should_inject_csp_nonce = True
    settings.security_hsts_enabled_effective = True
    settings.security_hsts_max_age = 3600
    settings.security_hsts_include_subdomains = True
    settings.security_hsts_preload = True
    settings.security_csp_report_only_effective = False
    settings.build_csp_policy.return_value = "default-src 'self'"
    settings.coop_enabled = True
    settings.coep_enabled = True
    settings.coep_header_value = "require-corp"
    settings.corp_enabled = True
    settings.corp_header_value = "same-origin"
    settings.security_x_frame_options = "DENY"
    settings.security_permissions_policy = "camera=()"
    settings.security_x_content_type_options = "nosniff"
    settings.security_referrer_policy = "no-referrer"

    middleware = SecurityHeadersMiddleware(app, settings=settings)

    async def call_next(req):
        return Response(content="<html>__CSP_NONCE__</html>", media_type="text/html")

    request = MagicMock(spec=Request)
    request.state = MagicMock()

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert "Strict-Transport-Security" in response.headers
    assert "Content-Security-Policy" in response.headers
    assert "Cross-Origin-Opener-Policy" in response.headers
    assert b"<html>" in response.body
    assert b"__CSP_NONCE__" not in response.body

    # Test with FileResponse and non-HTML
    async def call_next_json(req):
        return JSONResponse(content={"ok": True})

    response = await middleware.dispatch(request, call_next_json)
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers

    # Test injection with FileResponse (mocked)
    with patch("app.core.security_headers.Path") as mock_path:
        mock_path.return_value.read_bytes.return_value = b"<html>__CSP_NONCE__</html>"

        async def call_next_file(req):
            res = FileResponse(path="fake.html", media_type="text/html")
            return res

        response = await middleware.dispatch(request, call_next_file)
        assert b"__CSP_NONCE__" not in response.body
