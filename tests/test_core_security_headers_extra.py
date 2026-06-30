from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
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
    settings.build_csp_policy.side_effect = (
        lambda nonce=None,
        report_only=False: f"default-src 'self'; script-src 'nonce-{nonce}'"
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
