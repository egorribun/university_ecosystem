from importlib import util as importlib_util

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.core.config import Settings


@pytest.mark.anyio
async def test_strict_security_headers_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings()
    assert settings.strict_security_headers_enabled
    spec = importlib_util.find_spec("app.core.security_headers")
    assert spec and spec.origin
    module = importlib_util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)
    middleware_cls = module.SecurityHeadersMiddleware
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"status": "ok"}

    app.add_middleware(middleware_cls, settings=settings)

    transport = httpx.ASGITransport(app=app)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/")

    headers = response.headers
    hsts = headers.get("Strict-Transport-Security", "")
    assert "max-age=" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert (
        headers.get("Permissions-Policy") == "geolocation=(), microphone=(), camera=()"
    )
    assert headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert headers.get("Cross-Origin-Embedder-Policy") == "require-corp"
    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "upgrade-insecure-requests" in csp
    assert "img-src 'self' data:" in csp
    assert "script-src 'self' 'nonce-" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "https://api.spotify.com" in csp
    assert "https://fcm.googleapis.com" in csp
    assert "https://fcmregistrations.googleapis.com" in csp
    assert "https://*.push.services.mozilla.com" in csp
    assert "worker-src 'self' blob:" in csp
    assert "manifest-src 'self'" in csp
    assert "Content-Security-Policy-Report-Only" not in headers


def _reset_security_env(monkeypatch):
    for key in (
        "FRONTEND_ORIGINS",
        "CORS_ALLOW_CREDENTIALS",
        "ENABLE_STRICT_SECURITY_HEADERS",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", "")
    monkeypatch.setenv("APP_BASE_URL", "")


def test_cors_hardening_filters_insecure_origins(monkeypatch):
    _reset_security_env(monkeypatch)
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "FRONTEND_ORIGINS",
        "https://app.example.com, http://example.com, *",
    )
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    settings = Settings()
    assert settings.cors_allow_origins_list == ["https://app.example.com"]
    assert settings.cors_allow_credentials_effective is True


def test_cors_credentials_disabled_for_insecure_hosts(monkeypatch):
    _reset_security_env(monkeypatch)
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://example.com")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    settings = Settings()
    assert settings.cors_allow_origins_list == []
    assert settings.cors_allow_credentials_effective is False


def test_cors_allows_localhost_when_strict(monkeypatch):
    _reset_security_env(monkeypatch)
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    settings = Settings()
    assert settings.cors_allow_origins_list == ["http://localhost:5173"]
    assert settings.cors_allow_credentials_effective is True
