from __future__ import annotations

import uuid as _uuid_module
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from brotli_asgi import BrotliMiddleware
from fastapi import Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.csrf import CSRFMiddleware
from app.core.exceptions.handlers import asgi_json_problem
from app.core.internal_access import InternalAccessMiddleware
from app.core.localization import resolve_locale
from app.core.logging import bind_context, get_logger
from app.core.ratelimit import EndpointRateLimit, RateLimitMiddleware, parse_rate_limit
from app.core.security_headers import SecurityHeadersMiddleware

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except ImportError:  # pragma: no cover
    ProxyHeadersMiddleware: Any = None  # type: ignore[no-redef]

if TYPE_CHECKING:
    from typing import Any

    from fastapi import FastAPI, Request

    from app.core.config import Settings

_logger = get_logger(__name__)

# D-04 (audit 2026-03-08): Correlation ID available to any logger in this process
# via request_id_ctx.get().  Set by RequestIDMiddleware on every HTTP request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

_REQUEST_ID_SAFE_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


class RequestIDMiddleware:
    """Inject X-Request-ID into request scope and response headers.

    Accepts a client-supplied ``X-Request-ID`` header (useful for distributed
    tracing across services) or generates a fresh UUID4 when absent.

    The value is:
    - sanitised (only alphanum + ``-`` ``_``, max 64 chars) to prevent header
      injection via a crafted client header;
    - stored in ``request.state.request_id`` for use in route handlers;
    - propagated to loggers via the ``request_id_ctx`` ContextVar;
    - echoed back in the ``X-Request-ID`` response header so callers can
      correlate logs across FastAPI, ws-hub, and file-processor.

    Implemented as a raw ASGI callable (not BaseHTTPMiddleware) so streaming
    responses (SSE, NDJSON) are never buffered.  (D-04: audit 2026-03-08)
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        raw_id = request.headers.get("x-request-id", "")
        # Sanitise: keep only safe characters, truncate to 64, fall back to UUID4
        sanitised = "".join(c for c in raw_id if c in _REQUEST_ID_SAFE_CHARS)[:64]
        request_id = sanitised or str(_uuid_module.uuid4())

        scope.setdefault("state", {})["request_id"] = request_id
        ctx_token = request_id_ctx.set(request_id)
        # Binds request_id to the current asyncio task context for structlog.
        bind_context(request_id=request_id)

        async def _send_with_id(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, _send_with_id)
        finally:
            request_id_ctx.reset(ctx_token)


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

    # _BAD_CONTENT_LENGTH_BODY: bytes = b'{"detail":"Invalid Content-Length header"}'

    # @staticmethod
    # def _bad_content_length_response() -> Response:
    #     """Return a fresh response per call to prevent header pollution."""
    #     return Response(
    #         content=ContentSizeLimitMiddleware._BAD_CONTENT_LENGTH_BODY,
    #         status_code=400,
    #         media_type="application/json",
    #     )

    def __init__(self, app: Any, *, max_bytes: int = 50 * 1024 * 1024) -> None:
        """Initialise the middleware.

        Parameters
        ----------
        max_bytes:
            Upper body size limit in bytes.  Defaults to 50 MB to match the
            nginx Ingress ``proxy-body-size: "50m"`` annotation
            (k8s/ingress.yaml).  Both values MUST remain in sync — if you
            change one, update the other.
            RZ-08 (audit 2026-03-04): mismatched limits (5 MB here, 50 MB at
            Ingress) allowed requests between those sizes to bypass the fast
            Nginx gate and be rejected deep inside ASGI after fully streaming
            the body, wasting bandwidth and backend memory.
        """
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Fast path: Content-Length declared → reject immediately, no body read.
        cl_header = request.headers.get("content-length")
        if cl_header is not None:
            try:
                cl = int(cl_header)
            except ValueError:
                locale = resolve_locale(request=request)
                await asgi_json_problem(
                    request.scope["asgi"]["send"],
                    status_code=status.HTTP_400_BAD_REQUEST,
                    title_key="titles.bad_request",
                    detail_key="errors.config.invalid_content_length",
                    locale=locale,
                    instance=str(request.url),
                )
                return Response(
                    status_code=status.HTTP_400_BAD_REQUEST
                )  # Dummy response to satisfy type checker
            if cl > self._max_bytes:
                locale = resolve_locale(request=request)
                await asgi_json_problem(
                    request.scope["asgi"]["send"],
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    title_key="titles.bad_request",
                    detail_key="errors.config.payload_too_large",
                    locale=locale,
                    instance=str(request.url),
                    limit=self._max_bytes // (1024 * 1024),
                )
                return Response(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                )  # Dummy response to satisfy type checker

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
            if new_request:
                request = new_request

        return await call_next(request)

    # PERF-1: Threshold below which body is kept in RAM; beyond this it spills to
    # a temporary disk file.  100 concurrent 4.9 MB uploads without this threshold
    # would allocate ~490 MB of heap at once.  SpooledTemporaryFile transparently
    # handles the in-memory → disk transition so replay semantics are unchanged.
    _MEM_BUFFER_THRESHOLD: int = 512 * 1024  # 512 KB

    async def _read_and_replay_body(
        self, request: Request
    ) -> tuple[Request | None, Response | None]:
        """Consume request body safely within limits and return an injected replay Request.

        Bodies ≤ _MEM_BUFFER_THRESHOLD bytes are kept in RAM; larger bodies spill
        to a NamedTemporaryFile so concurrent uploads don't exhaust the heap.
        """
        import tempfile

        import anyio

        # PERF-006 (audit 2026-03-10): SpooledTemporaryFile() may create a real
        # temp file on disk when data exceeds max_size — a blocking open() syscall.
        # Run construction in a thread pool to keep the event loop responsive.
        _threshold = self._MEM_BUFFER_THRESHOLD
        tmpfile = await anyio.to_thread.run_sync(
            lambda: tempfile.SpooledTemporaryFile(max_size=_threshold, mode="w+b")
        )
        accumulated = 0
        try:
            async for chunk in request.stream():
                accumulated += len(chunk)
                if accumulated > self._max_bytes:
                    await anyio.to_thread.run_sync(tmpfile.close)
                    locale = resolve_locale(request=request)
                    await asgi_json_problem(
                        request.scope["asgi"]["send"],
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        title_key="titles.bad_request",
                        detail_key="errors.config.payload_too_large",
                        locale=locale,
                        instance=str(request.url),
                        limit=self._max_bytes // (1024 * 1024),
                    )
                    return None, Response(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                    )
                await anyio.to_thread.run_sync(tmpfile.write, chunk)

            await anyio.to_thread.run_sync(tmpfile.seek, 0)
            body_bytes = await anyio.to_thread.run_sync(tmpfile.read)
        finally:
            if not tmpfile.closed:
                await anyio.to_thread.run_sync(tmpfile.close)

        async def _replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        return Request(request.scope, receive=_replay_receive), None

    # @staticmethod
    # def _oversized_response(limit: int) -> JSONResponse:
    #     return JSONResponse(
    #         status_code=413,
    #         content={"detail": f"Payload Too Large (max {limit // (1024 * 1024)} MB)"},
    #     )


def _ensure_vary_header(response: Response, header_name: str) -> None:
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = header_name
        return
    values = [value.strip() for value in existing.split(",") if value.strip()]
    if header_name not in values:
        values.append(header_name)
        response.headers["Vary"] = ", ".join(values)


async def _http_response_hardening(
    request: Request, call_next: Callable[[Request], Coroutine[Any, Any, Response]]
) -> Response:
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

    # D-04 (audit 2026-03-08): Registered first so the correlation ID is
    # available to every downstream middleware and route handler.
    # Starlette applies add_middleware() in LIFO order, so this executes last
    # in the wrapping chain — which means it runs FIRST on incoming requests.
    app.add_middleware(RequestIDMiddleware)

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
    # Bearer-token callers are auto-exempted inside CSRFMiddleware.dispatch()
    # by detecting an Authorization: Bearer … header — no path exemption needed.
    # RZ-10 (audit 2026-03-04): /api/v1/auth/login was previously exempt.
    # RZ-01 (audit 2026-03-04): /api/v1/auth/logout was exempt — removed.
    #   Attackers could cross-site POST to /logout and force-logout any visiting
    #   authenticated user. The SPA sends X-CSRF-Token; Bearer clients are
    #   auto-exempted by the Authorization header check in CSRFMiddleware.
    app.add_middleware(
        CSRFMiddleware,
        exempt_prefixes=(
            "/internal",
            "/api/v1/csp-report",
            "/api/v2/auth/token",  # OAuth2 password/refresh grant
            "/api/v2/auth/webauthn",  # WebAuthn challenge/response flow
        ),
        cookie_secure=settings.cookie_secure,
        cookie_samesite=settings.cookie_samesite,
        # AUTH-01 (audit 2026-03-08): CSRF token must be short-lived to match the
        # access token lifetime.  Without this, the cookie persists 24h after
        # logout/session expiry, creating a CSRF replay window.
        cookie_max_age=settings.access_token_expire_minutes * 60,
        # RZ-003 (audit 2026-03-10): Pass the HMAC signing key so tokens are
        # bound to the session_id (Signed Double-Submit Cookie pattern).
        # When empty, CSRFMiddleware falls back to unsigned Double-Submit with a warning.
        csrf_hmac_secret=settings.csrf_hmac_secret,
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

    # Build endpoint-specific limits from settings
    endpoint_limits = []

    # Mapping of common prefixes to their respective settings
    limit_map = {
        "/api/v1/news": settings.rate_limit_news,
        "/api/v1/events": settings.rate_limit_events,
        "/api/v1/chat": settings.rate_limit_chat,
        "/api/v1/auth/login": settings.rate_limit_auth_login,
        "/api/v1/auth/register": settings.rate_limit_auth_register,
        "/api/v1/password/forgot": settings.rate_limit_auth_password_reset,
        "/api/v1/users/me": settings.rate_limit_users_me,
        "/graphql": settings.rate_limit_graphql,
    }

    for pattern, limit_str in limit_map.items():
        if limit_str:
            limit_val, window_val = parse_rate_limit(limit_str, fallback=(60, 60))
            if limit_val is not None:
                endpoint_limits.append(
                    EndpointRateLimit(pattern, limit_val, window_val)
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
                endpoint_limits=tuple(endpoint_limits),
            )
        elif rate_limit_backend == "memory" or normalized_url.startswith("memory://"):
            app.add_middleware(
                RateLimitMiddleware,
                redis_url=None,
                limit=default_limit,
                window_seconds=default_window,
                headers_enabled=settings.rate_limit_headers_enabled,
                storage_backend="memory",
                endpoint_limits=tuple(endpoint_limits),
            )

    if ProxyHeadersMiddleware is not None:
        # trusted_proxies_list = actual IP/CIDR of the load-balancer / ingress.
        # These are the ONLY IPs whose X-Forwarded-For headers we should trust.
        # (trusted_hosts_list is for TrustedHostMiddleware's Host-header check —
        #  it holds hostnames, not proxy IPs, and must NOT be used here.)
        trusted_proxy_ips = settings.trusted_proxies_list
        if trusted_proxy_ips:
            app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_proxy_ips)
        elif settings.environment not in {"development", "local", "testing"}:
            _logger.warning(
                "TRUSTED_PROXIES not configured. X-Forwarded-For will NOT be "
                "trusted. Set TRUSTED_PROXIES to your reverse-proxy CIDR/IP in .env."
            )

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
        max_bytes=getattr(settings, "max_upload_body_bytes", 50 * 1024 * 1024),
    )
