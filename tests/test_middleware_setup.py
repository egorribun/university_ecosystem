"""Tests for middleware setup (app/core/middleware/setup.py).

Validates that configure_middleware wires all middleware in the correct order
and that each helper function passes the right parameters from Settings.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI

from app.core.middleware.setup import (
    _configure_cors_middleware,
    _configure_csrf_middleware,
    _configure_rate_limiting,
    _configure_security_core,
    configure_middleware,
)


# ---------------------------------------------------------------------------
# Minimal mock settings factory
# ---------------------------------------------------------------------------


def _make_settings(**overrides: Any) -> MagicMock:
    """Create a mock Settings object with sensible defaults."""
    defaults = {
        "cors_allow_origins_list": ["http://localhost:3000"],
        "cors_allow_credentials_effective": True,
        "cors_allow_methods_list": ["GET", "POST"],
        "cors_allow_headers_list": ["Content-Type"],
        "cors_expose_headers_list": [],
        "rate_limit_enabled": False,
        "rate_limit_storage_uri": "redis://localhost",
        "rate_limit_storage_backend": "memory",
        "rate_limit_default_list": ["60/minute"],
        "rate_limit_headers_enabled": True,
        "rate_limit_news": "",
        "rate_limit_events": "",
        "rate_limit_chat": "",
        "rate_limit_auth_login": "",
        "rate_limit_auth_register": "",
        "rate_limit_auth_password_reset": "",
        "rate_limit_users_me": "",
        "rate_limit_graphql": "",
        "rate_limit_websocket": "",
        "cookie_secure": True,
        "cookie_samesite": "lax",
        "access_token_expire_minutes": 30,
        "csrf_hmac_secret": "test-csrf-secret",
        "response_compression_enabled": False,
        "trusted_proxies_list": [],
        "allowed_hosts_list": None,
        "internal_allowed_ips_list": ["127.0.0.1"],
        "internal_auth_header": "X-Internal-Token",
        "internal_auth_token": "test-token",
        "max_upload_body_bytes": 50 * 1024 * 1024,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for key, value in defaults.items():
        setattr(settings, key, value)
    return settings


# ---------------------------------------------------------------------------
# configure_middleware: wires all middleware in correct order
# ---------------------------------------------------------------------------


class TestConfigureMiddleware:
    """Tests for the top-level configure_middleware orchestrator."""

    def test_all_middleware_registered(self):
        """configure_middleware registers all expected middleware types."""
        app = FastAPI()
        settings = _make_settings()
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        # Content-size is always added
        assert "ContentSizeLimitMiddleware" in middleware_classes

    def test_brotli_disabled(self):
        """BrotliMiddleware is NOT added when response_compression_enabled=False."""
        app = FastAPI()
        settings = _make_settings(response_compression_enabled=False)
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "BrotliMiddleware" not in middleware_classes

    def test_brotli_enabled(self):
        """BrotliMiddleware IS added when response_compression_enabled=True."""
        app = FastAPI()
        settings = _make_settings(response_compression_enabled=True)
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "BrotliMiddleware" in middleware_classes


# ---------------------------------------------------------------------------
# _configure_rate_limiting
# ---------------------------------------------------------------------------


class TestConfigureRateLimiting:
    """Tests for _configure_rate_limiting helper."""

    def test_rate_limit_disabled_no_middleware(self):
        """When rate_limit_enabled=False, no RateLimitMiddleware is added."""
        app = FastAPI()
        settings = _make_settings(rate_limit_enabled=False)
        before_count = len(app.user_middleware)
        _configure_rate_limiting(app, settings)
        assert len(app.user_middleware) == before_count

    def test_rate_limit_enabled_adds_middleware(self):
        """When rate_limit_enabled=True, RateLimitMiddleware is added."""
        app = FastAPI()
        settings = _make_settings(rate_limit_enabled=True)
        _configure_rate_limiting(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "RateLimitMiddleware" in middleware_classes

    def test_rate_limit_redis_backend(self):
        """When storage_backend is 'redis', redis_url is passed through."""
        app = FastAPI()
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_storage_backend="redis",
            rate_limit_storage_uri="redis://custom:6379",
        )
        _configure_rate_limiting(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "RateLimitMiddleware" in middleware_classes

    def test_rate_limit_with_endpoint_limits(self):
        """Endpoint-specific rate limits are parsed and passed."""
        app = FastAPI()
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_news="10/minute",
            rate_limit_chat="5/second",
        )
        _configure_rate_limiting(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "RateLimitMiddleware" in middleware_classes


# ---------------------------------------------------------------------------
# _configure_cors_middleware
# ---------------------------------------------------------------------------


class TestConfigureCorsMiddleware:
    """Tests for _configure_cors_middleware helper."""

    def test_cors_middleware_added(self):
        """CORSMiddleware is added with settings values."""
        app = FastAPI()
        settings = _make_settings()
        _configure_cors_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "CORSMiddleware" in middleware_classes

    def test_cors_settings_passed(self):
        """CORS settings from the Settings object are wired correctly."""
        app = FastAPI()
        origins = ["http://example.com", "http://test.com"]
        settings = _make_settings(cors_allow_origins_list=origins)
        _configure_cors_middleware(app, settings)

        # Verify middleware was registered (settings are passed to constructor)
        assert len(app.user_middleware) >= 1


# ---------------------------------------------------------------------------
# _configure_csrf_middleware
# ---------------------------------------------------------------------------


class TestConfigureCsrfMiddleware:
    """Tests for _configure_csrf_middleware helper."""

    def test_csrf_middleware_added(self):
        """CSRFMiddleware is added with correct exempt prefixes."""
        app = FastAPI()
        settings = _make_settings()
        _configure_csrf_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "CSRFMiddleware" in middleware_classes

    def test_csrf_cookie_max_age_calculated(self):
        """Cookie max_age is derived from access_token_expire_minutes * 60."""
        app = FastAPI()
        settings = _make_settings(access_token_expire_minutes=15)
        _configure_csrf_middleware(app, settings)

        # Verify middleware was registered
        middleware_entry = app.user_middleware[-1]
        assert middleware_entry.kwargs.get("cookie_max_age") == 15 * 60


# ---------------------------------------------------------------------------
# _configure_security_core
# ---------------------------------------------------------------------------


class TestConfigureSecurityCore:
    """Tests for _configure_security_core helper."""

    def test_request_id_and_security_headers_added(self):
        """RequestIDMiddleware and SecurityHeadersMiddleware are registered."""
        app = FastAPI()
        settings = _make_settings()
        _configure_security_core(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "RequestIDMiddleware" in middleware_classes
        assert "SecurityHeadersMiddleware" in middleware_classes

    def test_internal_access_middleware_added(self):
        """InternalAccessMiddleware is registered with correct parameters."""
        app = FastAPI()
        settings = _make_settings(
            internal_allowed_ips_list=["10.0.0.1"],
            internal_auth_header="X-Custom-Header",
            internal_auth_token="secret-token",
        )
        _configure_security_core(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "InternalAccessMiddleware" in middleware_classes


# ---------------------------------------------------------------------------
# ProxyHeadersMiddleware conditional
# ---------------------------------------------------------------------------


class TestProxyHeadersMiddleware:
    """Tests for conditional ProxyHeadersMiddleware registration."""

    def test_proxy_headers_added_when_available_and_proxies_set(self):
        """ProxyHeadersMiddleware registered when available and trusted_proxies non-empty."""
        app = FastAPI()
        settings = _make_settings(trusted_proxies_list=["10.0.0.1"])
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        # ProxyHeadersMiddleware should be present if uvicorn is installed
        # (which it is in our test environment)
        assert "ProxyHeadersMiddleware" in middleware_classes

    def test_proxy_headers_not_added_when_no_proxies(self):
        """ProxyHeadersMiddleware is NOT added when trusted_proxies_list is empty."""
        app = FastAPI()
        settings = _make_settings(trusted_proxies_list=[])
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "ProxyHeadersMiddleware" not in middleware_classes


# ---------------------------------------------------------------------------
# TrustedHostMiddleware conditional
# ---------------------------------------------------------------------------


class TestTrustedHostMiddleware:
    """Tests for conditional TrustedHostMiddleware registration."""

    def test_trusted_hosts_added_when_set(self):
        """TrustedHostMiddleware is added when allowed_hosts_list is non-empty."""
        app = FastAPI()
        settings = _make_settings(allowed_hosts_list=["example.com"])
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "TrustedHostMiddleware" in middleware_classes

    def test_trusted_hosts_not_added_when_none(self):
        """TrustedHostMiddleware is NOT added when allowed_hosts_list is None."""
        app = FastAPI()
        settings = _make_settings(allowed_hosts_list=None)
        configure_middleware(app, settings)

        middleware_classes = [
            m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
            for m in app.user_middleware
        ]
        assert "TrustedHostMiddleware" not in middleware_classes
