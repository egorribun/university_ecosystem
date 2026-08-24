"""Proxy to expose middleware setup hook externally without circular dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.csrf import CSRFMiddleware
from app.core.internal_access import InternalAccessMiddleware
from app.core.ratelimit import EndpointRateLimit, RateLimitMiddleware, parse_rate_limit
from app.core.security_headers import SecurityHeadersMiddleware

from .content_size import ContentSizeLimitMiddleware
from .request_id import RequestIDMiddleware
from .response_hardening import http_response_hardening
from .tenant import TenantContextMiddleware

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except ImportError:
    ProxyHeadersMiddleware: Any = None  # type: ignore[no-redef]

if TYPE_CHECKING:
    from app.core.config import Settings


def _configure_security_core(app: FastAPI, settings: Settings) -> None:
    # D-04 (audit 2026-03-08): Registered first so the correlation ID is
    # available to every downstream middleware and route handler.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        TenantContextMiddleware,
        internal_hmac_secret=settings.internal_hmac_secret,
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    # Internal Access — only allowed IPs & tokens.
    app.add_middleware(
        InternalAccessMiddleware,
        allowed_ips=settings.internal_allowed_ips_list,
        header_name=settings.internal_auth_header,
        header_token=settings.internal_auth_token,
        internal_prefixes=INTERNAL_ROUTE_PREFIXES,
    )


def _configure_csrf_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CSRFMiddleware,
        exempt_prefixes=(
            "/internal",
            "/api/v1/csp-report",
            "/api/v2/auth/token",
            "/api/v2/auth/webauthn",
        ),
        cookie_secure=settings.cookie_secure,
        cookie_samesite=settings.cookie_samesite,
        cookie_max_age=settings.access_token_expire_minutes * 60,
        csrf_hmac_secret=settings.csrf_hmac_secret,
    )


def _configure_rate_limiting(app: FastAPI, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return

    # TD-14-04 (audit Wave 14): Extracted to named constant — was hardcoded
    # as (60, 60) in two places.
    _DEFAULT_RATE_LIMIT_FALLBACK = (60, 60)

    rate_limit_url = settings.rate_limit_storage_uri.strip()
    rate_limit_backend = settings.rate_limit_storage_backend.strip().lower()
    rate_limit_defaults = settings.rate_limit_default_list
    default_limit, default_window = parse_rate_limit(
        rate_limit_defaults[0] if rate_limit_defaults else None,
        fallback=_DEFAULT_RATE_LIMIT_FALLBACK,
    )

    limit_map = {
        "/api/v1/news": settings.rate_limit_news,
        "/api/v1/events": settings.rate_limit_events,
        "/api/v1/chat": settings.rate_limit_chat,
        "/api/v1/auth/login": settings.rate_limit_auth_login,
        "/api/v1/auth/register": settings.rate_limit_auth_register,
        "/api/v1/password/forgot": settings.rate_limit_auth_password_reset,
        "/api/v1/users/me": settings.rate_limit_users_me,
        "/graphql": settings.rate_limit_graphql,
        "/ws": settings.rate_limit_websocket,
    }

    endpoint_limits = []
    for pattern, limit_str in limit_map.items():
        if limit_str:
            limit_val, window_val = parse_rate_limit(
                limit_str, fallback=_DEFAULT_RATE_LIMIT_FALLBACK
            )
            if limit_val is not None:
                endpoint_limits.append(
                    EndpointRateLimit(pattern, limit_val, window_val)
                )

    storage_backend = "redis" if rate_limit_backend == "redis" else "memory"
    redis_url = rate_limit_url if storage_backend == "redis" else None

    app.add_middleware(
        RateLimitMiddleware,
        redis_url=redis_url,
        limit=default_limit,
        window_seconds=default_window,
        headers_enabled=settings.rate_limit_headers_enabled,
        storage_backend=storage_backend,
        endpoint_limits=tuple(endpoint_limits),
    )


def _configure_cors_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials_effective,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
        expose_headers=settings.cors_expose_headers_list,
    )


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    """Configure all application middlewares. (TD-004 decomposed)"""

    # 1. Base Security & ID
    _configure_security_core(app, settings)

    # 2. Performance (Brotli)
    if settings.response_compression_enabled:
        app.add_middleware(
            BrotliMiddleware, minimum_size=512, gzip_fallback=True, quality=5
        )

    # 3. Cross-Site Protection
    _configure_csrf_middleware(app, settings)

    # 4. Custom response hardening
    app.middleware("http")(http_response_hardening)

    # 5. Rate Limiting
    _configure_rate_limiting(app, settings)

    # 6. Proxy & Host Validation
    if ProxyHeadersMiddleware is not None and (
        trusted_proxies := settings.trusted_proxies_list
    ):
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_proxies)

    if allowed_hosts := getattr(settings, "allowed_hosts_list", None):
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # 7. CORS
    _configure_cors_middleware(app, settings)

    # 8. Request Guards (Size limit wraps EVERYTHING)
    app.add_middleware(
        ContentSizeLimitMiddleware,
        max_bytes=getattr(settings, "max_upload_body_bytes", 50 * 1024 * 1024),
    )
