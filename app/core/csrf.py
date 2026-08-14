"""CSRF protection via the Signed Double-Submit Cookie pattern.

How it works (Signed Double-Submit — OWASP §Signed Double-Submit Cookies)
--------------------------------------------------------------------------
1. On every response the middleware ensures a ``csrf_token`` cookie is
   present.  The cookie value is a signed token::

       <random_nonce>.<HMAC-SHA256(random_nonce + session_id, hmac_secret)>

   Binding the HMAC to the current *session ID* prevents the "subdomain
   fixation" attack: an adversary who controls ``static.university.edu``
   can set arbitrary cookies on the parent domain, but cannot compute a
   valid MAC for the victim's session ID without the server-side secret.

2. The cookie is **not** HttpOnly so the browser-resident SPA can read it
   and forward it as the ``X-CSRF-Token`` header on mutating requests.

3. On state-changing requests (POST / PUT / PATCH / DELETE) the middleware
   verifies:
   a. The header token matches the cookie token (classic Double-Submit).
   b. The HMAC is valid for the nonce *and* the current session ID.
      An attacker-crafted cookie with a known nonce but wrong session_id
      will fail the HMAC check — subdomain fixation is closed.

Unsigned fallback (dev / no secret configured)
----------------------------------------------
When ``csrf_hmac_secret`` is empty (local dev without .env), the middleware
falls back transparently to the classic unsigned Double-Submit pattern so
the application still boots without requiring extra configuration.  A
warning is logged once on startup.  Production should always set the secret.

Exemptions (in priority order)
-------------------------------
* ``OPTIONS`` — preflight; no body, no side-effects.
* WebSocket upgrades (Upgrade: websocket header) — long-lived, no cookies.
* ``Authorization: Bearer …`` — REST/mobile API clients; CORS guards them.
* Configurable ``exempt_prefixes`` — /internal, OAuth callbacks, etc.

Implementation: pure ASGI (no BaseHTTPMiddleware)
--------------------------------------------------
Using ``BaseHTTPMiddleware`` buffers the **entire response body** in memory
before passing it downstream, silently breaking SSE and chunked uploads.
This implementation is a pure ASGI callable that injects the CSRF cookie
via the ``http.response.start`` ASGI message without reading or buffering
any response body.  (TD-2: audit 2026-02-26)
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import TYPE_CHECKING

from starlette.requests import Request

from app.core.exceptions.handlers import asgi_json_problem
from app.core.localization import resolve_locale
from app.core.logging import get_logger
from app.core.middleware import request_id_ctx  # TD-09 (audit Wave 12)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_logger = get_logger(__name__)

_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
# Nonce bytes: 256-bit → 43 URL-safe base64 chars
_TOKEN_NONCE_BYTES = 32
# Separator between nonce and HMAC in the cookie value.
# Period is safe in cookie values (RFC 6265) and is not produced by base64url.
_TOKEN_SEPARATOR = "."  # nosec B105  # noqa: S105

# RZ-W9-04: Anonymous session binding cookie.
# Replaces the previous IP+UA fingerprint with a random per-client nonce so
# that users behind shared NAT/CDN (same IP + identical UA) get independent
# CSRF tokens and cannot cross-forge requests for each other.
_ANON_NONCE_COOKIE_NAME = "_csrf_anon_nonce"
_ANON_NONCE_HEX_LEN = 32  # secrets.token_hex(16) → 32 lowercase hex chars
_ANON_NONCE_RE = re.compile(
    r"^[0-9a-f]{32}$"
)  # RZ-28-02: compiled regex for uniform-time validation
_ANON_NONCE_MAX_AGE = 3600  # 1 hour — matches typical pre-login session lifetime
# State key to carry a newly-generated nonce from _extract_session_id to
# send_with_csrf_cookie so the cookie can be set in the same response.
_NEW_ANON_NONCE_STATE_KEY = "_csrf_new_anon_nonce"

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
    setattr(request.state, _ROTATE_CSRF_KEY, True)


# ── HMAC helpers ─────────────────────────────────────────────────────────────


def _compute_csrf_hmac(nonce: str, session_id: str, secret: bytes) -> str:
    """Return the hex-encoded HMAC-SHA256(nonce + session_id, secret).

    Binding the HMAC to session_id prevents subdomain fixation:
    a subdomain adversary can set the nonce but cannot compute a valid MAC
    for a victim's session_id without knowing the server secret.
    """
    message = (nonce + session_id).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _build_signed_token(session_id: str, secret: bytes) -> str:
    """Generate a signed CSRF token: ``<nonce>.<hmac>``."""
    nonce = secrets.token_urlsafe(_TOKEN_NONCE_BYTES)
    mac = _compute_csrf_hmac(nonce, session_id, secret)
    return f"{nonce}{_TOKEN_SEPARATOR}{mac}"


def _verify_signed_token(token: str, session_id: str, secret: bytes) -> bool:
    """Verify a signed CSRF token in constant time.

    Returns True iff the token is well-formed and the HMAC is valid for the
    given session_id. Always O(1) regardless of early-exit conditions to
    prevent timing oracles.
    """
    # Split into exactly two parts — reject malformed tokens.
    parts = token.split(_TOKEN_SEPARATOR, maxsplit=1)
    if len(parts) != 2:
        return False
    nonce, received_mac = parts
    if not nonce or not received_mac:
        return False
    expected_mac = _compute_csrf_hmac(nonce, session_id, secret)
    # secrets.compare_digest is constant-time on equal-length strings.
    return secrets.compare_digest(expected_mac, received_mac)


# ── Session ID extraction ─────────────────────────────────────────────────────


def _extract_session_id(request: Request, cookie_token: str) -> str:
    """Return the session identifier to bind into the CSRF HMAC.

    Priority (most specific → least specific):
    1. ``request.state.session_id`` — set by the auth middleware after the
       JWT is validated.  This is the tightest binding.
    2. ``_csrf_anon_nonce`` cookie — a random per-client nonce for anonymous
       users that survives across requests within the same browser session.
       RZ-W9-04: Replaces the previous IP+UA fingerprint.  IP+UA caused CSRF
       token collisions for users sharing a corporate NAT/CDN with identical
       User-Agents; a random nonce is unique per browser instance.
    """
    session_id: str = getattr(request.state, "session_id", None) or ""
    if not session_id:
        # Read the persisted per-client nonce from the dedicated cookie.
        anon_nonce = request.cookies.get(_ANON_NONCE_COOKIE_NAME, "")
        # Validate: must be exactly _ANON_NONCE_HEX_LEN lowercase hex chars.
        # RZ-27-06: Always call token_hex to normalize timing regardless of
        # cookie validity. Discarded when the cookie is valid.
        # RZ-28-02: Replaced short-circuit boolean chain with compiled regex
        # fullmatch for more uniform validation timing.
        fresh_nonce = secrets.token_hex(16)
        if not (anon_nonce and _ANON_NONCE_RE.fullmatch(anon_nonce)):
            # Generate a fresh nonce and store it in request.state so that
            # send_with_csrf_cookie can include the Set-Cookie in the response.
            anon_nonce = fresh_nonce
            setattr(request.state, _NEW_ANON_NONCE_STATE_KEY, anon_nonce)
        session_id = f"anon:{anon_nonce}"
    return session_id


async def _reject_csrf(scope: Scope, receive: Receive, send: Send) -> None:
    """Return a localized 403 JSON response for CSRF rejection."""
    locale = resolve_locale(request=Request(scope, receive))
    await asgi_json_problem(
        send,
        status_code=403,
        title_key="titles.forbidden",
        detail_key="errors.csrf.mismatch",
        locale=locale,
        instance=str(scope.get("path", "")),
    )


class CSRFMiddleware:
    """Signed Double-Submit Cookie CSRF protection - pure ASGI.

    RZ-3 (audit Mar 2026): Upgraded from plain Double-Submit to Signed
    Double-Submit (OWASP CSRF Cheat Sheet §Signed Double-Submit Cookies).
    Each CSRF token is now HMAC-SHA256 signed and bound to the current
    session_id, closing the subdomain fixation attack vector.

    When `csrf_hmac_secret` is not configured (empty), the middleware
    falls back gracefully to the unsigned Double-Submit pattern to keep
    local development working without extra environment variables.

    Implemented as a raw ASGI callable (no `BaseHTTPMiddleware`) so that
    streaming responses (SSE, NDJSON, chunked file downloads) are never
    buffered into memory.  The CSRF cookie is injected into the
    `http.response.start` message without touching the response body.
    (TD-2: audit 2026-02-26)

    Parameters
    ----------
    exempt_prefixes:
        URL path prefixes that bypass CSRF validation entirely (e.g.
        `["/internal", "/api/v2/auth/token"]`).
    cookie_secure:
        Whether to set the `Secure` flag on the CSRF cookie.  Should
        be `True` in production (HTTPS-only).
    cookie_samesite:
        `SameSite` policy for the CSRF cookie.  `"strict"` is
        preferred in production; `"lax"` may be needed in development
        when the frontend and API run on different ports.
    csrf_hmac_secret:
        HMAC key used to sign tokens.  If empty, falls back to unsigned
        Double-Submit (with a startup warning).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_prefixes: Sequence[str] = (),
        cookie_secure: bool = True,
        cookie_samesite: str = "strict",
        cookie_max_age: int = 86400,
        csrf_hmac_secret: str = "",
    ) -> None:
        self._app = app
        self._exempt: tuple[str, ...] = tuple(exempt_prefixes)
        self._cookie_secure = cookie_secure
        self._cookie_samesite = cookie_samesite
        # RZ-F-08 (audit 2026-03-07): Explicit Max-Age prevents the CSRF token
        # from becoming a permanent session cookie — browsers restore session
        # cookies on restart, which would effectively make them permanent.
        self._cookie_max_age = cookie_max_age

        # RZ-003 / RZ-NEW-004 (audit 2026-03-19): Derive bytes key at construction.
        # RZ-W18-02 (audit 2026-03-23 Wave 18): validate byte length, not char length.
        if csrf_hmac_secret:
            secret_bytes = csrf_hmac_secret.encode("utf-8")
            if len(secret_bytes) < 32:  # HMAC-SHA256 requires >=32 bytes of entropy
                raise ValueError(
                    f"CSRF_HMAC_SECRET is too short ({len(secret_bytes)} bytes after "
                    "UTF-8 encoding). Minimum 32 bytes required for HMAC-SHA256 "
                    "security margin. Generate with: "
                    'python -c "import secrets; print(secrets.token_hex(32))"'
                )
            self._hmac_key: bytes = secret_bytes
            self._signed: bool = True
        else:
            # RZ-NEW-004: Fail-fast in non-development environments.
            # A warning-only downgrade is unacceptable in production: operators
            # may not review logs for hours, leaving the app vulnerable to
            # subdomain fixation attacks (OWASP CSRF Cheat Sheet).
            from app.core.config import settings as _csrf_settings

            _csrf_env: str = getattr(
                _csrf_settings, "environment", "production"
            ).lower()
            _csrf_dev_envs: frozenset[str] = frozenset(
                {"development", "local", "testing", "test"}
            )
            if _csrf_env not in _csrf_dev_envs:
                raise RuntimeError(
                    "CSRF_HMAC_SECRET must be configured in non-development environments. "
                    "Unsigned CSRF fallback is NOT acceptable in production "
                    "(subdomain fixation attack vector — OWASP CSRF Cheat Sheet). "
                    'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            # Graceful unsigned fallback for local dev only — warn once.
            self._hmac_key = b""
            self._signed = False
            _logger.warning(
                "RZ-003: CSRF signing key is not configured. "
                "Falling back to unsigned Double-Submit pattern (development only).",
                vulnerability="subdomain fixation",
                recommendation="Configure the CSRF signing key in production.",
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure

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
        # RZ-4 (audit 2026-03-05): Use the HTTP Upgrade header (RFC 6455) rather
        # than path prefix matching. path.startswith("/ws") is fragile — any route
        # like /wsadmin or /wsreport would silently bypass CSRF protection.
        # The Upgrade header is the canonical, protocol-level indicator of a WS handshake.
        if request.headers.get("upgrade", "").lower() == "websocket":
            await self._app(scope, receive, send)
            return

        # Configurable exemptions (internal routes, OAuth callbacks, etc.).
        if self._exempt and path.startswith(self._exempt):
            await self._app(scope, receive, send)
            return

        # Bearer-token clients (mobile apps, CLI tools, API consumers) authenticate
        # with the Authorization header, not cookies. Cross-site requests cannot forge
        # an Authorization header via HTML forms or img/script tags — only explicit
        # XHR/fetch with cors credentials can, which is already blocked by CORS policy.
        auth_header = request.headers.get("authorization", "")
        # RZ-NEW-003: Bypass CSRF ONLY if no authentication cookie is present.
        # If a user is logged in via cookie, we MUST verify CSRF regardless of Bearer presence,
        # because browsers will auto-attach the cookie on cross-origin requests.
        has_auth_cookie = bool(
            request.cookies.get("access_token_v2")
            or request.cookies.get("access_token")
            or request.cookies.get("session_id")
        )
        if auth_header.lower().startswith("bearer ") and not has_auth_cookie:
            await self._app(scope, receive, send)
            return

        # ── Core CSRF validation ──────────────────────────────────────────────
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_token = request.headers.get(CSRF_HEADER_NAME, "")

        if method in _MUTATION_METHODS:
            if not cookie_token or not header_token:
                _logger.warning(
                    "CSRF rejected (missing CSRF proof)",
                    method=method,
                    path=path,
                    cookie_present=bool(cookie_token),
                    header_present=bool(header_token),
                    request_id=request_id_ctx.get(""),
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                await _reject_csrf(scope, receive, send)
                return

            # Step 1: Classic Double-Submit — constant-time comparison.
            if not secrets.compare_digest(cookie_token, header_token):
                _logger.warning(
                    "CSRF rejected (CSRF proof mismatch)",
                    method=method,
                    path=path,
                    request_id=request_id_ctx.get(""),
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                await _reject_csrf(scope, receive, send)
                return

            # Step 2: HMAC signature check (RZ-003 — Signed Double-Submit).
            # Only performed when the secret is configured (signed mode).
            if self._signed:
                session_id = _extract_session_id(request, cookie_token)
                if not _verify_signed_token(cookie_token, session_id, self._hmac_key):
                    _logger.warning(
                        "CSRF rejected (invalid HMAC signature)",
                        method=method,
                        path=path,
                        request_id=request_id_ctx.get(""),
                    )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                    await _reject_csrf(scope, receive, send)
                    return

        # ── Inject CSRF cookie into response (no body buffering) ─────────────
        async def send_with_csrf_cookie(message: Message) -> None:
            """Inject Set-Cookie into http.response.start without buffering body."""
            if message["type"] == "http.response.start":
                should_rotate: bool = getattr(request.state, _ROTATE_CSRF_KEY, False)
                # If no existing cookie is present, or the endpoint signaled rotation, inject a new token
                if not cookie_token or should_rotate:
                    if self._signed:
                        session_id = _extract_session_id(request, "")
                        new_token = _build_signed_token(session_id, self._hmac_key)
                    else:
                        new_token = secrets.token_urlsafe(_TOKEN_NONCE_BYTES)
                    set_cookie_header = self._build_set_cookie_header(new_token)
                    headers: list[tuple[bytes, bytes]] = list(
                        message.get("headers", [])
                    )
                    headers.append((b"set-cookie", set_cookie_header))
                    # RZ-W9-04: If a new anonymous nonce was generated in
                    # _extract_session_id (i.e. the client had no existing
                    # _csrf_anon_nonce cookie), persist it as a separate
                    # HttpOnly cookie so future requests can reuse the same
                    # binding nonce without regenerating it every time.
                    new_anon_nonce: str | None = getattr(
                        request.state, _NEW_ANON_NONCE_STATE_KEY, None
                    )
                    if new_anon_nonce:
                        headers.append(
                            (
                                b"set-cookie",
                                self._build_anon_nonce_cookie(new_anon_nonce),
                            )
                        )
                    message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, send_with_csrf_cookie)

    def _build_set_cookie_header(self, token: str) -> bytes:
        """Build a raw ``Set-Cookie`` header value for the CSRF token."""
        parts = [
            f"{CSRF_COOKIE_NAME}={token}",
            "Path=/",
            f"Max-Age={self._cookie_max_age}",
            "SameSite=" + self._cookie_samesite,
        ]
        if self._cookie_secure:
            parts.append("Secure")
        # HttpOnly is intentionally OMITTED — the SPA must read this cookie
        # in JavaScript to forward it as the X-CSRF-Token request header.
        return "; ".join(parts).encode("latin-1")

    def _build_anon_nonce_cookie(self, nonce: str) -> bytes:
        """Build a raw ``Set-Cookie`` header value for the anonymous session nonce.

        RZ-W9-04: Unlike the CSRF token, the nonce cookie IS HttpOnly — the
        SPA never needs to read it directly; it is only used server-side as the
        HMAC binding for anonymous users.  SameSite=Strict prevents it from
        being sent on cross-site navigations.
        """
        parts = [
            f"{_ANON_NONCE_COOKIE_NAME}={nonce}",
            "Path=/",
            f"Max-Age={_ANON_NONCE_MAX_AGE}",
            "SameSite=" + self._cookie_samesite,
            "HttpOnly",
        ]
        if self._cookie_secure:
            parts.append("Secure")
        return "; ".join(parts).encode("latin-1")
