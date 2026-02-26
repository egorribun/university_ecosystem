from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from brotli_asgi import BrotliMiddleware
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.csrf import CSRFMiddleware
from app.core.internal_access import InternalAccessMiddleware
from app.core.rate_limit import RateLimitMiddleware, parse_rate_limit
from app.core.security_headers import SecurityHeadersMiddleware

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except ImportError:  # pragma: no cover
    ProxyHeadersMiddleware: Any = None  # type: ignore[no-redef]

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

    from app.core.config import Settings

_logger = logging.getLogger(__name__)


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject HTTP requests whose body exceeds *max_bytes*.

    Provides defence-in-depth on top of upstream proxy limits (nginx / caddy).
    Handles both Content-Length and chunked Transfer-Encoding so attackers
    cannot bypass the check by omitting the header.

    Body replay: when the body is streamed (no Content-Length), this middleware
    buffers the chunks, enforces the limit, and then replaces the ASGI `receive`
    callable with a replay that returns the buffered body.  Without this, the
    downstream handler would receive an already-exhausted stream (empty body),
    which is a silent, hard-to-debug data-loss bug. (TD-2: audit 2026-02-24)
    """

    _BAD_CONTENT_LENGTH_BODY: bytes = b'{"detail":"Invalid Content-Length header"}'

    @staticmethod
    def _bad_content_length_response() -> Response:
        """Return a fresh response per call to prevent header pollution."""
        return Response(
            content=ContentSizeLimitMiddleware._BAD_CONTENT_LENGTH_BODY,
            status_code=400,
            media_type="application/json",
        )

    def __init__(self, app, *, max_bytes: int = 5 * 1024 * 1024) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        # Fast path: Content-Length declared → reject immediately, no body read.
        cl_header = request.headers.get("content-length")
        if cl_header is not None:
            try:
                cl = int(cl_header)
            except ValueError:
                return self._bad_content_length_response()
            if cl > self._max_bytes:
                return self._oversized_response(self._max_bytes)

        # Slow path: chunked / unknown length — stream, accumulate, replay.
        # Extend to DELETE because RFC 9110 permits DELETE with a body, and
        # payloads without Content-Length would bypass the fast path.
        method = request.method.upper()
        path = request.url.path or ""
        has_body = method in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith(
            "/ws"
        )
        if has_body and cl_header is None:
            new_request, error_response = await self._read_and_replay_body(request)
            if error_response:
                return error_response
            request = new_request

        from fastapi import Response

        return cast(Response, await call_next(request))

    # PERF-1: Threshold below which body is kept in RAM; beyond this it spills to
    # a temporary disk file.  100 concurrent 4.9 MB uploads without this threshold
    # would allocate ~490 MB of heap at once.  SpooledTemporaryFile transparently
    # handles the in-memory → disk transition so replay semantics are unchanged.
    _MEM_BUFFER_THRESHOLD: int = 512 * 1024  # 512 KB

    async def _read_and_replay_body(self, request: Request):
        """Consume request body safely within limits and return an injected replay Request.

        Bodies ≤ _MEM_BUFFER_THRESHOLD bytes are kept in RAM; larger bodies spill
        to a NamedTemporaryFile so concurrent uploads don't exhaust the heap.
        """
        import tempfile

        accumulated = 0
        with tempfile.SpooledTemporaryFile(
            max_size=self._MEM_BUFFER_THRESHOLD, mode="w+b"
        ) as tmpfile:
            async for chunk in request.stream():
                accumulated += len(chunk)
                if accumulated > self._max_bytes:
                    return None, self._oversized_response(self._max_bytes)
                tmpfile.write(chunk)

            tmpfile.seek(0)
            body_bytes = tmpfile.read()

        async def _replay_receive() -> dict:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        return Request(request.scope, receive=_replay_receive), None

    @staticmethod
    def _oversized_response(limit: int) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Payload Too Large (max {limit // (1024 * 1024)} MB)"},
        )


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


def configure_middleware(app: FastAPI, settings: Settings) -> None:
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

    # CSRF double-submit cookie protection for browser-based clients.
    # Exempt: /ws (WebSocket), /internal (token-guarded), OAuth token endpoint.
    # Bearer-token callers are auto-exempted inside CSRFMiddleware.dispatch().
    app.add_middleware(
        CSRFMiddleware,
        exempt_prefixes=(
            "/internal",
            "/api/v1/csp-report",
            "/api/v1/auth/logout",
            "/api/v2/auth/token",  # OAuth2 password/refresh grant
            "/api/v2/auth/webauthn",  # WebAuthn challenge/response flow
        ),
        cookie_secure=settings.cookie_secure,
        cookie_samesite=settings.cookie_samesite,
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

    if ProxyHeadersMiddleware is not None:
        trusted_hosts = settings.trusted_hosts_list
        if trusted_hosts:
            app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

    # TrustedHostMiddleware protects against Host Header injection attacks
    # by validating that incoming requests have an allowed Host header.
    allowed_hosts = getattr(settings, "allowed_hosts_list", None)
    if allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts,
        )
        _logger.debug("TrustedHostMiddleware configured with hosts: %s", allowed_hosts)

    _logger.debug("CORS Origins configured: %s", settings.cors_allow_origins_list)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials_effective,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
        expose_headers=settings.cors_expose_headers_list,
    )

    # Body-size guard: reject oversized payloads before they reach route handlers.
    # Added last so it wraps all other middleware (Starlette applies in reverse).
    app.add_middleware(
        ContentSizeLimitMiddleware,
        max_bytes=getattr(settings, "max_upload_body_bytes", 5 * 1024 * 1024),
    )
