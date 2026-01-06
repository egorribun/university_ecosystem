from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.internal_access import InternalAccessMiddleware
from app.core.rate_limit import RateLimitMiddleware, parse_rate_limit
from app.core.sanitization import SanitizationMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:
    ProxyHeadersMiddleware = None

if TYPE_CHECKING:
    from app.core.config import AppSettings

_logger = logging.getLogger(__name__)


def _ensure_vary_header(response, header_name: str) -> None:
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = header_name
        return
    values = [value.strip() for value in existing.split(",") if value.strip()]
    if header_name not in values:
        values.append(header_name)
        response.headers["Vary"] = ", ".join(values)


async def _http_response_hardening(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        # Encourage browsers to keep avatars locally without marking them immutable.
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    acao = response.headers.get("access-control-allow-origin")
    if acao and acao != "*":
        _ensure_vary_header(response, "Origin")
        if request.method.upper() == "OPTIONS":
            _ensure_vary_header(response, "Access-Control-Request-Method")
            if request.headers.get("access-control-request-headers"):
                _ensure_vary_header(response, "Access-Control-Request-Headers")
    return response


def configure_middleware(app: FastAPI, settings: AppSettings) -> None:
    """Configure all application middlewares."""

    _RESPONSE_COMPRESSION_MINIMUM_SIZE = 512

    if settings.response_compression_enabled:
        app.add_middleware(
            BrotliMiddleware,
            minimum_size=_RESPONSE_COMPRESSION_MINIMUM_SIZE,
            gzip_fallback=True,
            quality=5,
        )

    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    # Input sanitization middleware for defense-in-depth
    app.add_middleware(
        SanitizationMiddleware,
        enabled=True,
        skip_paths=("/api/internal/",),
    )

    app.add_middleware(
        InternalAccessMiddleware,
        allowed_ips=settings.internal_allowed_ips_list,
        header_name=settings.internal_auth_header,
        header_token=settings.internal_auth_token,
        internal_prefixes=INTERNAL_ROUTE_PREFIXES,
    )

    app.middleware("http")(_http_response_hardening)

    rate_limit_url = settings.rate_limit_storage_uri.strip()
    rate_limit_backend = settings.rate_limit_storage_backend.strip().lower()
    rate_limit_defaults = settings.rate_limit_default_list
    default_limit, default_window = parse_rate_limit(
        rate_limit_defaults[0] if rate_limit_defaults else None,
        fallback=(60, 60),
    )

    if settings.rate_limit_enabled:
        normalized_url = rate_limit_url.lower()
        if rate_limit_backend == "redis" and normalized_url.startswith(
            ("redis://", "rediss://")
        ):
            app.add_middleware(
                RateLimitMiddleware,
                redis_url=rate_limit_url,
                limit=default_limit,
                window_seconds=default_window,
                headers_enabled=settings.rate_limit_headers_enabled,
                storage_backend="redis",
            )
        elif rate_limit_backend == "memory" or normalized_url.startswith("memory://"):
            app.add_middleware(
                RateLimitMiddleware,
                redis_url=None,
                limit=default_limit,
                window_seconds=default_window,
                headers_enabled=settings.rate_limit_headers_enabled,
                storage_backend="memory",
            )

    if ProxyHeadersMiddleware:
        trusted_hosts = settings.trusted_hosts_list
        if trusted_hosts:
            app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

    _logger.debug("CORS Origins configured: %s", settings.cors_allow_origins_list)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials_effective,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
        expose_headers=settings.cors_expose_headers_list,
    )
