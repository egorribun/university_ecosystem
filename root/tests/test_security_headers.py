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
    assert headers.get("Strict-Transport-Security")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert (
        headers.get("Permissions-Policy") == "geolocation=(), microphone=(), camera=()"
    )
    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
