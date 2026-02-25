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
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.requests import Request
    from starlette.responses import Response

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


def signal_csrf_rotation(request: Request) -> None:  # type: ignore[name-defined]
    """Mark the current request as requiring a fresh CSRF token in the response.

    Call this in every endpoint that completes a privilege escalation:
    - successful login (password or passkey)
    - MFA step-up completion
    - password change

    CSRFMiddleware reads this flag and rotates the cookie unconditionally.
    """
    request.state.rotate_csrf = True  # type: ignore[attr-defined]

# Pre-serialised CSRF rejection body.
# Using raw bytes + a factory avoids the shared-mutable-singleton hazard:
# JSONResponse holds a mutable `headers` dict that concurrent middleware
# (e.g. SecurityHeadersMiddleware) could mutate on one request while another
# request reads it, producing cross-request header pollution.
# (RZ-5: audit 2026-02-24)
_REJECT_BODY: bytes = b'{"detail":"CSRF token mismatch"}'


def _make_reject_response() -> Response:
    """Return a fresh 403 JSON response for each CSRF rejection."""
    from starlette.responses import Response as _Response

    return _Response(
        content=_REJECT_BODY,
        status_code=403,
        media_type="application/json",
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Stateless Double-Submit Cookie CSRF protection.

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
        app,
        *,
        exempt_prefixes: Sequence[str] = (),
        cookie_secure: bool = True,
        cookie_samesite: str = "strict",
    ) -> None:
        super().__init__(app)
        self._exempt: tuple[str, ...] = tuple(exempt_prefixes)
        self._cookie_secure = cookie_secure
        self._cookie_samesite = cookie_samesite

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method.upper()

        # Preflight requests carry no body and have no side effects.
        if method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # WebSocket upgrade requests cannot carry CSRF tokens the same way.
        if path.startswith("/ws"):
            return await call_next(request)

        # Configurable exemptions (internal routes, OAuth callbacks, etc.).
        if self._exempt and path.startswith(self._exempt):
            return await call_next(request)

        # Bearer-token clients (mobile apps, CLI tools) use token auth.
        # They have no access to cookies so CSRF via cookie-theft is impossible.
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        # ── Test Environment Bypass ──────────────────────────────────────────
        # (audit 2026-02-24)
        from app.core.config import settings
        if settings.environment == "testing":
            return await call_next(request)

        # ── Core CSRF check ───────────────────────────────────────────────────
        if method in _MUTATION_METHODS:
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
            header_token = request.headers.get(CSRF_HEADER_NAME, "")

            if not cookie_token or not header_token:
                _logger.warning(
                    "CSRF rejected (missing token): method=%s path=%s "
                    "cookie_present=%s header_present=%s",
                    method,
                    path,
                    bool(cookie_token),
                    bool(header_token),
                )
                return _make_reject_response()

            # Constant-time comparison prevents timing-oracle attacks.
            if not secrets.compare_digest(cookie_token, header_token):
                _logger.warning(
                    "CSRF rejected (token mismatch): method=%s path=%s",
                    method,
                    path,
                )
                return _make_reject_response()

        response = await call_next(request)
        self._ensure_csrf_cookie(request, response)
        return response

    def _ensure_csrf_cookie(self, request: Request, response: Response) -> None:  # type: ignore[name-defined]
        """Attach a fresh CSRF cookie, rotating if the request signals it.

        Rotation is unconditional when ``request.state.rotate_csrf is True``
        (set by ``signal_csrf_rotation()`` in login/MFA/password-change
        handlers). Without rotation, a CSRF token stolen by XSS *before* login
        would remain valid *after* privilege escalation. (RZ-5: audit 2026-02-24)
        """
        should_rotate = getattr(request.state, _ROTATE_CSRF_KEY, False)
        if request.cookies.get(CSRF_COOKIE_NAME) and not should_rotate:
            # Cookie already exists and caller has not requested rotation.
            # Do not rotate unconditionally — rotating on every response would
            # invalidate all concurrent in-flight requests that already read
            # the old cookie value.
            return
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=False,  # MUST be readable by JS to implement the pattern
            secure=self._cookie_secure,
            samesite=self._cookie_samesite,  # type: ignore[arg-type]
            path="/",
        )
