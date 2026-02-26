"""CSRF protection via the stateless Double-Submit Cookie pattern.

How it works
------------
1. On every response the middleware ensures a ``csrf_token`` cookie is
   present.  The cookie is **not** HttpOnly so the browser-resident SPA
   can read it with JavaScript and attach it as the ``X-CSRF-Token``
   request header on every mutating request.
2. On state-changing requests (POST / PUT / PATCH / DELETE) the
   middleware verifies that the ``X-CSRF-Token`` header matches the
   ``csrf_token`` cookie value.  An attacker on a different origin cannot
   read the cookie, so they cannot forge the header — this is the core
   invariant of the pattern.

Exemptions (in priority order)
-------------------------------
* ``OPTIONS`` — preflight; no body, no side-effects.
* Paths starting with ``/ws`` — WebSocket upgrade requests are
  long-lived and do not transmit cookies in the same way.
* ``Authorization: Bearer …`` — REST / mobile API clients use
  token-based auth and have no access to browser cookies.
* Configurable ``exempt_prefixes`` — e.g. ``/internal``, OAuth callbacks.

SameSite relationship
---------------------
``SameSite=Strict`` on the *authentication* cookie already blocks most
CSRF vectors in modern browsers.  This middleware is a defence-in-depth
layer that also covers older browsers, same-site subdomain compromise,
and development environments where ``SameSite=lax`` is used.

Implementation: pure ASGI (no BaseHTTPMiddleware)
--------------------------------------------------
Using ``BaseHTTPMiddleware`` from Starlette buffers the **entire response
body** in memory before passing it downstream.  This silently breaks
streaming responses (SSE, NDJSON, chunked upload progress) and inflates
peak memory for large file downloads.

This implementation is a pure ASGI callable that injects the CSRF cookie
via the ``http.response.start`` ASGI message without reading or buffering
any response body.  (TD-2: audit 2026-02-26)
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_logger = logging.getLogger(__name__)

_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
_TOKEN_BYTES = 32  # 256-bit token → ~43 URL-safe base64 chars

# Marker key in request.state used by auth endpoints to signal that the CSRF
# token must be rotated after privilege escalation (login, MFA completion,
# password change).  Call signal_csrf_rotation(request) in those handlers.
# (RZ-5: audit 2026-02-24)
_ROTATE_CSRF_KEY = "rotate_csrf"


def signal_csrf_rotation(request: Request) -> None:
    """Mark the current request as requiring a fresh CSRF token in the response.

    Call this in every endpoint that completes a privilege escalation:
    - successful login (password or passkey)
    - MFA step-up completion
    - password change

    CSRFMiddleware reads this flag and rotates the cookie unconditionally.
    """
    request.state.rotate_csrf = True


# Pre-serialised CSRF rejection body.
# Using raw bytes + a factory avoids the shared-mutable-singleton hazard:
# JSONResponse holds a mutable `headers` dict that concurrent middleware
# (e.g. SecurityHeadersMiddleware) could mutate on one request while another
# request reads it, producing cross-request header pollution.
# (RZ-5: audit 2026-02-24)
_REJECT_BODY: bytes = b'{"detail":"CSRF token mismatch"}'


def _make_reject_response() -> Response:
    """Return a fresh 403 JSON response for each CSRF rejection."""
    return Response(
        content=_REJECT_BODY,
        status_code=403,
        media_type="application/json",
    )


class CSRFMiddleware:
    """Stateless Double-Submit Cookie CSRF protection — pure ASGI.

    Implemented as a raw ASGI callable (no ``BaseHTTPMiddleware``) so that
    streaming responses (SSE, NDJSON, chunked file downloads) are never
    buffered into memory.  The CSRF cookie is injected into the
    ``http.response.start`` message without touching the response body.
    (TD-2: audit 2026-02-26)

    Parameters
    ----------
    exempt_prefixes:
        URL path prefixes that bypass CSRF validation entirely (e.g.
        ``["/internal", "/api/v2/auth/token"]``).
    cookie_secure:
        Whether to set the ``Secure`` flag on the CSRF cookie.  Should
        be ``True`` in production (HTTPS-only).
    cookie_samesite:
        ``SameSite`` policy for the CSRF cookie.  ``"strict"`` is
        preferred in production; ``"lax"`` may be needed in development
        when the frontend and API run on different ports.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_prefixes: Sequence[str] = (),
        cookie_secure: bool = True,
        cookie_samesite: str = "strict",
    ) -> None:
        self._app = app
        self._exempt: tuple[str, ...] = tuple(exempt_prefixes)
        self._cookie_secure = cookie_secure
        self._cookie_samesite = cookie_samesite

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only protect HTTP — pass WebSocket / lifespan through unchanged.
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method.upper()

        # ── Fast-path exemptions ──────────────────────────────────────────────
        # Preflight — no body, no side-effects.
        if method == "OPTIONS":
            await self._app(scope, receive, send)
            return

        path: str = request.url.path

        # WebSocket upgrade requests cannot carry CSRF tokens the same way.
        if path.startswith("/ws"):
            await self._app(scope, receive, send)
            return

        # Configurable exemptions (internal routes, OAuth callbacks, etc.).
        if self._exempt and path.startswith(self._exempt):
            await self._app(scope, receive, send)
            return

        # Bearer-token clients (mobile apps, CLI tools) use token auth.
        # They have no access to cookies so CSRF via cookie-theft is impossible.
        # However, we must ensure that a browser SPA isn't explicitly sending a
        # Bearer token alongside its cookies to maliciously bypass CSRF validation.
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            if not request.cookies.get(CSRF_COOKIE_NAME):
                await self._app(scope, receive, send)
                return

        # ── Core CSRF validation ──────────────────────────────────────────────
        if method in _MUTATION_METHODS:
            cookie_token: str = request.cookies.get(CSRF_COOKIE_NAME, "")
            header_token: str = request.headers.get(CSRF_HEADER_NAME, "")

            if not cookie_token or not header_token:
                _logger.warning(
                    "CSRF rejected (missing token): method=%s path=%s "
                    "cookie_present=%s header_present=%s",
                    method,
                    path,
                    bool(cookie_token),
                    bool(header_token),
                )
                reject = _make_reject_response()
                await reject(scope, receive, send)
                return

            # Constant-time comparison prevents timing-oracle attacks.
            if not secrets.compare_digest(cookie_token, header_token):
                _logger.warning(
                    "CSRF rejected (token mismatch): method=%s path=%s",
                    method,
                    path,
                )
                reject = _make_reject_response()
                await reject(scope, receive, send)
                return

        # ── Inject CSRF cookie into response (no body buffering) ─────────────
        existing_cookie: str = request.cookies.get(CSRF_COOKIE_NAME, "")

        async def send_with_csrf_cookie(message: Message) -> None:
            """Inject Set-Cookie into http.response.start without buffering body."""
            if message["type"] == "http.response.start":
                should_rotate: bool = getattr(request.state, _ROTATE_CSRF_KEY, False)
                # If no existing cookie is present, or the endpoint signaled rotation, inject a new token
                if not existing_cookie or should_rotate:
                    new_token = secrets.token_urlsafe(_TOKEN_BYTES)
                    set_cookie_header = self._build_set_cookie_header(new_token)
                    headers: list[tuple[bytes, bytes]] = list(
                        message.get("headers", [])
                    )
                    headers.append((b"set-cookie", set_cookie_header))
                    message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, send_with_csrf_cookie)

    def _build_set_cookie_header(self, token: str) -> bytes:
        """Build a raw ``Set-Cookie`` header value for the CSRF token."""
        parts = [
            f"{CSRF_COOKIE_NAME}={token}",
            "Path=/",
            "SameSite=" + self._cookie_samesite,
        ]
        if self._cookie_secure:
            parts.append("Secure")
        # HttpOnly is intentionally OMITTED — the SPA must read this cookie
        # in JavaScript to forward it as the X-CSRF-Token request header.
        return "; ".join(parts).encode("latin-1")
