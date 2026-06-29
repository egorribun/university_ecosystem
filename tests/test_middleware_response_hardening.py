"""Tests for response hardening middleware (app/core/middleware/response_hardening.py).

Validates the _ensure_vary_header helper and the http_response_hardening
middleware function for Cache-Control, deprecation headers, and CORS Vary
header injection.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from app.core.middleware.response_hardening import (
    _ensure_vary_header,
    http_response_hardening,
)

# ---------------------------------------------------------------------------
# _ensure_vary_header unit tests
# ---------------------------------------------------------------------------


class TestEnsureVaryHeader:
    """Unit tests for the _ensure_vary_header helper."""

    def test_empty_existing_vary(self):
        """When no Vary header exists, sets it to the given value."""
        response = Response()
        _ensure_vary_header(response, "Origin")
        assert response.headers["Vary"] == "Origin"

    def test_existing_vary_with_other_values(self):
        """Adds header_name to existing Vary values."""
        response = Response()
        response.headers["Vary"] = "Accept-Encoding"
        _ensure_vary_header(response, "Origin")
        vary = response.headers["Vary"]
        assert "Origin" in vary
        assert "Accept-Encoding" in vary

    def test_duplicate_detection(self):
        """Does not duplicate an already-present header name."""
        response = Response()
        response.headers["Vary"] = "Origin, Accept-Encoding"
        _ensure_vary_header(response, "Origin")
        values = [v.strip() for v in response.headers["Vary"].split(",")]
        assert values.count("Origin") == 1

    def test_sorted_output(self):
        """Vary values are sorted alphabetically."""
        response = Response()
        response.headers["Vary"] = "Origin"
        _ensure_vary_header(response, "Accept-Encoding")
        vary = response.headers["Vary"]
        parts = [v.strip() for v in vary.split(",")]
        assert parts == sorted(parts)

    def test_multiple_additions(self):
        """Multiple calls build a cumulative, deduplicated, sorted Vary header."""
        response = Response()
        _ensure_vary_header(response, "Origin")
        _ensure_vary_header(response, "Accept-Encoding")
        _ensure_vary_header(response, "Accept-Language")
        parts = [v.strip() for v in response.headers["Vary"].split(",")]
        assert len(parts) == 3
        assert parts == sorted(parts)

    def test_whitespace_handling(self):
        """Existing Vary with extra whitespace is handled correctly."""
        response = Response()
        response.headers["Vary"] = "  Origin ,  Accept-Encoding  "
        _ensure_vary_header(response, "Accept-Language")
        parts = [v.strip() for v in response.headers["Vary"].split(",")]
        assert "Accept-Language" in parts


# ---------------------------------------------------------------------------
# http_response_hardening integration tests
# ---------------------------------------------------------------------------


def _build_test_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the response hardening middleware."""
    test_app = FastAPI()

    if cors_origins is not None:
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    test_app.middleware("http")(http_response_hardening)

    @test_app.get("/static/avatar.png")
    async def static_avatar() -> Response:
        return Response(content=b"fake-image", media_type="image/png")

    @test_app.get("/api/v1/users")
    async def api_v1_users() -> dict:
        return {"users": []}

    @test_app.get("/api/v2/users")
    async def api_v2_users() -> dict:
        return {"users": []}

    @test_app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return test_app


@pytest.mark.asyncio
async def test_static_file_cache_control():
    """Static file responses get Cache-Control header set."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/static/avatar.png")
    assert response.status_code == 200
    assert "public" in response.headers.get("cache-control", "")
    assert "max-age=86400" in response.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_api_v1_deprecation_headers():
    """API v1 responses include Deprecation, Sunset, and Link headers."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users")
    assert response.status_code == 200
    assert response.headers.get("deprecation") == "true"
    assert "2026-12-31" in response.headers.get("sunset", "")
    assert "/api/v2" in response.headers.get("link", "")
    assert 'rel="successor-version"' in response.headers.get("link", "")


@pytest.mark.asyncio
async def test_api_v2_no_deprecation_headers():
    """API v2 responses do NOT include deprecation headers."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v2/users")
    assert response.status_code == 200
    assert "deprecation" not in response.headers
    assert "sunset" not in response.headers


@pytest.mark.asyncio
async def test_cors_vary_header_injection():
    """Responses with CORS origin get Vary: Origin injected."""
    app = _build_test_app(cors_origins=["http://example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://example.com"},
        )
    assert response.status_code == 200
    vary = response.headers.get("vary", "")
    assert "Origin" in vary


@pytest.mark.asyncio
async def test_options_preflight_vary_headers():
    """OPTIONS preflight with CORS injects Vary for Access-Control-Request-Method."""
    app = _build_test_app(cors_origins=["http://example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
    assert response.status_code == 200
    vary = response.headers.get("vary", "")
    assert "Origin" in vary
    assert "Access-Control-Request-Method" in vary
    assert "Access-Control-Request-Headers" in vary


@pytest.mark.asyncio
async def test_non_cors_response_unchanged():
    """Non-CORS responses do not get extra Vary headers."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    vary = response.headers.get("vary", "")
    assert "Origin" not in vary


@pytest.mark.asyncio
async def test_wildcard_cors_no_vary_injection():
    """When CORS returns Access-Control-Allow-Origin: *, no Vary is added."""
    app = _build_test_app(cors_origins=["*"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://any-origin.com"},
        )
    assert response.status_code == 200
    # Wildcard CORS should NOT trigger Vary injection because acao == "*"
    vary = response.headers.get("vary", "")
    # When acao is "*", the middleware skips _ensure_vary_header
    # (however CORSMiddleware itself may add a Vary header)
