from importlib import util as importlib_util

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.core.config import Settings


@pytest.mark.anyio
async def test_security_headers_production_mode(monkeypatch):
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setenv("ENABLE_COOP", "true")
    monkeypatch.setenv("ENABLE_COEP", "true")
    monkeypatch.setenv("COEP_VALUE", "require-corp")
    monkeypatch.setenv("SECURITY_CSP_REPORT_ONLY", "false")
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
    assert "frame-ancestors 'self'" in csp
    assert "img-src 'self' data: blob:" in csp
    assert "script-src 'self' 'nonce-" in csp
    assert "'strict-dynamic'" in csp
    assert "'report-sample'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "https://api.spotify.com" in csp
    assert "https://fcm.googleapis.com" in csp
    assert "https://fcmregistrations.googleapis.com" in csp
    assert "https://*.push.services.mozilla.com" in csp
    assert "Content-Security-Policy-Report-Only" not in headers
    assert "trusted-types app dompurify-news goog#html 'allow-duplicates'" in csp
    assert "require-trusted-types-for 'script'" in csp


@pytest.mark.anyio
async def test_security_headers_development_report_only(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ENABLE_STRICT_SECURITY_HEADERS", raising=False)
    settings = Settings()
    assert not settings.strict_security_headers_enabled
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
    assert "Strict-Transport-Security" not in headers
    assert "Content-Security-Policy" not in headers
    report_only = headers.get("Content-Security-Policy-Report-Only", "")
    assert "default-src 'self'" in report_only
    expected_script = (
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "http://localhost:5173 'report-sample'"
    )
    assert expected_script in report_only
    assert (
        "trusted-types app dompurify-news goog#html 'allow-duplicates'" in report_only
    )
    assert "require-trusted-types-for 'script'" not in report_only
    assert "http://localhost:5173" in report_only
    assert "http://127.0.0.1:8000" in report_only
    assert "ws://localhost:5173" in report_only
    assert "Cross-Origin-Opener-Policy" not in headers
    assert "Cross-Origin-Embedder-Policy" not in headers


@pytest.mark.anyio
async def test_security_headers_credentialless_coep(monkeypatch):
    monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setenv("ENABLE_COEP", "true")
    monkeypatch.setenv("COEP_VALUE", "credentialless")
    settings = Settings()
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
    assert headers.get("Cross-Origin-Embedder-Policy") == "credentialless"


def _reset_security_env(monkeypatch):
    for key in (
        "FRONTEND_ORIGINS",
        "CORS_ALLOW_CREDENTIALS",
        "ENABLE_STRICT_SECURITY_HEADERS",
        "ENVIRONMENT",
        "ENABLE_COOP",
        "ENABLE_COEP",
        "COEP_VALUE",
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
