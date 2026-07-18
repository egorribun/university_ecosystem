"""Unit + middleware tests for CSRF Signed Double-Submit protection.

The existing ``tests/test_config_security.py`` exercises CSRF only as a
side-effect of broader middleware checks. This module covers
``app/core/csrf.py`` directly:

* HMAC helpers (``_compute_csrf_hmac`` / ``_build_signed_token`` /
  ``_verify_signed_token``) — deterministic + session binding,
* signed-token verification edge cases (malformed, empty parts,
  wrong session, wrong secret),
* anonymous-nonce regex behaviour (``_ANON_NONCE_RE`` — uniform-time
  validation),
* constructor invariants (short secret, missing secret in prod vs dev),
* middleware behaviour through a real ASGI transport — Bearer/cookie
  branches, mutating-method gating, cookie rotation on success,
  WebSocket upgrade bypass, and exempt-prefix bypass.

We keep the cookie/header constants centralised at the top of each test
group so the file stays readable even after CSRF internals shift.
"""

from __future__ import annotations

import re
import secrets
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI

from app.core.csrf import (
    _ANON_NONCE_COOKIE_NAME,
    _ANON_NONCE_HEX_LEN,
    _ANON_NONCE_RE,
    _ROTATE_CSRF_KEY,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRFMiddleware,
    _build_signed_token,
    _compute_csrf_hmac,
    _verify_signed_token,
    signal_csrf_rotation,
)

# A 32-byte HMAC secret that satisfies the constructor's minimum-entropy check.
# The literal value is irrelevant — we only need a stable bytes() input.
_TEST_SECRET = b"a" * 32


# ── 1. Pure HMAC helpers — deterministic, session-bound ──────────────────────


class TestComputeCsrfHmac:
    """``_compute_csrf_hmac`` is the keystone of subdomain-fixation defence."""

    def test_deterministic_for_same_inputs(self) -> None:
        """The same nonce + session_id + secret always yields the same MAC."""
        mac1 = _compute_csrf_hmac("nonce-A", "session-1", _TEST_SECRET)
        mac2 = _compute_csrf_hmac("nonce-A", "session-1", _TEST_SECRET)
        assert mac1 == mac2

    def test_changes_with_session_id(self) -> None:
        """Same nonce + different sessions → different MAC (subdomain defence)."""
        mac1 = _compute_csrf_hmac("nonce-A", "session-1", _TEST_SECRET)
        mac2 = _compute_csrf_hmac("nonce-A", "session-2", _TEST_SECRET)
        assert mac1 != mac2

    def test_changes_with_secret(self) -> None:
        """Different secret → different MAC."""
        mac1 = _compute_csrf_hmac("nonce-A", "session-1", _TEST_SECRET)
        mac2 = _compute_csrf_hmac("nonce-A", "session-1", b"b" * 32)
        assert mac1 != mac2

    def test_returns_64_hex_chars(self) -> None:
        """SHA-256 hex digest is exactly 64 lowercase hex chars."""
        mac = _compute_csrf_hmac("nonce", "session", _TEST_SECRET)
        assert len(mac) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", mac)


class TestBuildSignedToken:
    """``_build_signed_token`` produces ``<nonce>.<hmac>`` strings."""

    def test_format_nonce_dot_hmac(self) -> None:
        """The token is exactly two dot-separated parts."""
        token = _build_signed_token("session-1", _TEST_SECRET)
        parts = token.split(".")
        assert len(parts) == 2
        nonce, mac = parts
        assert nonce
        assert len(mac) == 64

    def test_uniqueness_per_call(self) -> None:
        """Each invocation produces a fresh nonce — tokens never collide."""
        tokens = {_build_signed_token("session-1", _TEST_SECRET) for _ in range(100)}
        assert len(tokens) == 100

    def test_signed_with_session_binding(self) -> None:
        """The token verifies for its session and only its session."""
        token = _build_signed_token("session-A", _TEST_SECRET)
        assert _verify_signed_token(token, "session-A", _TEST_SECRET) is True
        assert _verify_signed_token(token, "session-B", _TEST_SECRET) is False


class TestVerifySignedToken:
    """``_verify_signed_token`` is constant-time and reject malformed input."""

    def test_valid_token_passes(self) -> None:
        token = _build_signed_token("session-X", _TEST_SECRET)
        assert _verify_signed_token(token, "session-X", _TEST_SECRET) is True

    def test_rejects_wrong_session(self) -> None:
        """Subdomain-fixation defence: cookie set by attacker, victim's session."""
        token = _build_signed_token("victim-session", _TEST_SECRET)
        assert _verify_signed_token(token, "attacker-session", _TEST_SECRET) is False

    def test_rejects_wrong_secret(self) -> None:
        token = _build_signed_token("session", _TEST_SECRET)
        assert _verify_signed_token(token, "session", b"different" * 4) is False

    @pytest.mark.parametrize(
        "malformed",
        [
            "",  # empty
            "no-separator",  # no '.'
            ".",  # both halves empty
            ".onlymac",  # empty nonce
            "onlynonce.",  # empty mac
            "nonce.shortmac",  # mac wrong length (still constant-time, but != expected)
        ],
    )
    def test_rejects_malformed(self, malformed: str) -> None:
        """Malformed shapes never produce a true verification."""
        assert _verify_signed_token(malformed, "any-session", _TEST_SECRET) is False

    def test_rejects_token_with_extra_separators(self) -> None:
        """``maxsplit=1`` keeps the second segment intact, so MAC won't match."""
        # Build a real token then graft junk after a second '.' — verifies that
        # extra '.' chars in the MAC half (where they cannot legitimately appear
        # because hex-only output) cause verification failure.
        token = _build_signed_token("s", _TEST_SECRET)
        nonce, mac = token.split(".", 1)
        assert _verify_signed_token(f"{nonce}.{mac}.junk", "s", _TEST_SECRET) is False


# ── 2. Anonymous-nonce regex — uniform-time validation ──────────────────────


class TestAnonNonceRegex:
    """The regex backs CSRF anonymous-binding token validation."""

    def test_constant_length_lowercase_hex_passes(self) -> None:
        """Exactly 32 lowercase hex chars is the only accepted shape."""
        valid = secrets.token_hex(16)
        assert len(valid) == _ANON_NONCE_HEX_LEN
        assert _ANON_NONCE_RE.fullmatch(valid)

    @pytest.mark.parametrize(
        "candidate",
        [
            "",  # empty
            "short",  # too short
            "a" * 31,  # one char short
            "a" * 33,  # one char too long
            ("A" * 32),  # uppercase hex — must fail (uniform-time guarantee)
            ("g" * 32),  # 'g' is not hex
            "0" * 31 + "/",  # not hex
            "  " + "a" * 30,  # leading whitespace
        ],
    )
    def test_invalid_shapes_rejected(self, candidate: str) -> None:
        assert _ANON_NONCE_RE.fullmatch(candidate) is None

    def test_anon_cookie_name_is_stable(self) -> None:
        """The anonymous nonce cookie name is part of the public protocol contract."""
        assert _ANON_NONCE_COOKIE_NAME == "_csrf_anon_nonce"


# ── 3. signal_csrf_rotation ──────────────────────────────────────────────────


def test_signal_csrf_rotation_sets_state_flag() -> None:
    """The helper writes a single boolean flag into ``request.state``."""
    request = MagicMock()
    request.state = MagicMock(spec=[])  # empty state object
    signal_csrf_rotation(request)
    assert getattr(request.state, _ROTATE_CSRF_KEY) is True


# ── 4. Constructor invariants ────────────────────────────────────────────────


class _NoopApp:
    """Minimal ASGI app — used as the inner middleware target."""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})


def test_constructor_rejects_short_secret() -> None:
    """A <32-byte secret raises immediately — HMAC-SHA256 entropy floor."""
    with pytest.raises(ValueError, match="too short"):
        CSRFMiddleware(_NoopApp(), csrf_hmac_secret="short")


def test_constructor_rejects_empty_secret_in_production(monkeypatch) -> None:
    """In a non-development environment, an empty secret aborts boot."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="must be configured"):
        CSRFMiddleware(_NoopApp(), csrf_hmac_secret="")


def test_constructor_allows_empty_secret_in_test_env(monkeypatch) -> None:
    """In dev/test/local, the unsigned fallback boots with a logged warning."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "testing")
    mw = CSRFMiddleware(_NoopApp(), csrf_hmac_secret="")
    assert mw._signed is False  # type: ignore[attr-defined]
    assert mw._hmac_key == b""  # type: ignore[attr-defined]


def test_constructor_accepts_long_enough_secret() -> None:
    """A 32-byte secret enables signed mode."""
    mw = CSRFMiddleware(_NoopApp(), csrf_hmac_secret="x" * 32)
    assert mw._signed is True  # type: ignore[attr-defined]
    assert len(mw._hmac_key) == 32  # type: ignore[attr-defined]


# ── 5. Middleware behaviour via ASGITransport ────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/safe")
    async def _safe() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/mut")
    async def _mut() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/internal/health")
    async def _internal() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def _wrap(app: FastAPI, **kwargs: Any) -> FastAPI:
    """Wrap an app with CSRFMiddleware using sane test defaults."""
    defaults = {
        "csrf_hmac_secret": "x" * 32,
        "cookie_secure": False,  # test client uses plain http://
        "cookie_samesite": "lax",
    }
    defaults.update(kwargs)
    app.add_middleware(CSRFMiddleware, **defaults)
    return app


@pytest.mark.asyncio
async def test_get_sets_csrf_cookie() -> None:
    """A safe GET response carries a freshly-issued CSRF cookie."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/safe")
    assert response.status_code == 200
    assert CSRF_COOKIE_NAME in response.cookies
    # Token must be in the signed format.
    token = response.cookies[CSRF_COOKIE_NAME]
    assert "." in token


@pytest.mark.asyncio
async def test_post_rejects_when_cookie_missing() -> None:
    """A mutating request with no cookie or header is rejected with 403."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post("/mut")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_rejects_when_cookie_and_header_mismatch() -> None:
    """Header ≠ cookie → reject (constant-time compare)."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # Seed the cookie via a safe request first.
        await client.get("/safe")
        cookie = client.cookies.get(CSRF_COOKIE_NAME)
        assert cookie is not None
        # Forge a different header value.
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: "wrong-token"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_passes_when_cookie_and_header_match() -> None:
    """A correctly mirrored token in cookie + header is accepted."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.get("/safe")
        cookie = client.cookies.get(CSRF_COOKIE_NAME)
        assert cookie is not None
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: cookie})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_rejects_invalid_hmac_in_signed_mode() -> None:
    """Cookie/header agree but the HMAC fails — subdomain-fixation guard."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # Use a syntactically valid <nonce>.<mac> token but with a fabricated MAC.
        forged = "fake-nonce." + "0" * 64
        client.cookies.set(CSRF_COOKIE_NAME, forged)
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: forged})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_websocket_upgrade_header_bypasses() -> None:
    """An HTTP request with ``Upgrade: websocket`` is exempted from CSRF."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # POST to /mut with the websocket upgrade header — would normally 403.
        response = await client.post("/mut", headers={"Upgrade": "websocket"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_bearer_without_auth_cookie_bypasses() -> None:
    """A Bearer-token client (no auth cookie) skips CSRF validation."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/mut",
            headers={"Authorization": "Bearer token-abc"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_bearer_with_auth_cookie_still_validated() -> None:
    """Bearer + access_token cookie → CSRF must still be enforced."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        client.cookies.set("access_token", "logged-in-cookie")
        response = await client.post(
            "/mut",
            headers={"Authorization": "Bearer token-abc"},
        )
    # No CSRF token was provided → 403.
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_exempt_prefix_bypasses() -> None:
    """A configured exempt prefix passes through without CSRF gating."""
    app = _wrap(_make_app(), exempt_prefixes=["/internal"])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post("/internal/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_options_preflight_bypasses() -> None:
    """OPTIONS preflight (CORS) is never gated by CSRF."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.request("OPTIONS", "/mut")
    # FastAPI returns 405 for unsupported OPTIONS by default; the key invariant
    # is that the response is NOT a CSRF-403.
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_anonymous_nonce_cookie_persists_across_requests() -> None:
    """First GET issues an anon-nonce cookie; subsequent GETs reuse it."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.get("/safe")
        first_nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        assert first_nonce is not None
        assert _ANON_NONCE_RE.fullmatch(first_nonce)

        # Second request with the same client carries the cookie back.
        await client.get("/safe")
        second_nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        assert second_nonce == first_nonce


@pytest.mark.asyncio
async def test_unsigned_mode_accepts_matching_cookie_header(monkeypatch) -> None:
    """In unsigned/dev mode the classic Double-Submit still functions."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "testing")
    app = _make_app()
    app.add_middleware(CSRFMiddleware, csrf_hmac_secret="", cookie_secure=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.get("/safe")
        cookie = client.cookies.get(CSRF_COOKIE_NAME)
        assert cookie is not None
        # In unsigned mode the token has no '.' separator.
        assert "." not in cookie
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: cookie})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_csrf_websocket_scope_passthrough(monkeypatch) -> None:
    """Lines 299-301: CSRFMiddleware passes WebSocket scopes directly to the inner app.

    CSRF protection only applies to HTTP. WebSocket upgrades (scope['type'] == 'websocket')
    must pass through without CSRF validation. We verify this by sending a raw ASGI
    websocket scope through the middleware and confirming it reaches the inner app
    (which would raise on HTTP-only CSRF validation).
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "testing")

    # Create a minimal ASGI app to record what scope types pass through
    received_scopes: list[str] = []

    async def inner_app(scope, receive, send):
        received_scopes.append(scope["type"])
        # For WebSocket, we must at least respond with an accept
        if scope["type"] == "websocket":
            msg = await receive()
            if msg["type"] == "websocket.connect":
                await send({"type": "websocket.accept"})

    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "environment", "testing")
    csrf = CSRFMiddleware(
        inner_app,
        csrf_hmac_secret="",
        cookie_secure=False,
    )

    async def receive():
        return {"type": "websocket.connect"}

    sent_messages: list[dict] = []

    async def send(msg):
        sent_messages.append(msg)

    scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [],
        "query_string": b"",
        "asgi": {"version": "3.0"},
    }
    await csrf(scope, receive, send)

    # The WebSocket scope was passed to inner_app (no CSRF check applied)
    assert "websocket" in received_scopes


@pytest.mark.asyncio
async def test_csrf_cookie_secure_flag_set(monkeypatch) -> None:
    """Lines 431, 452: When cookie_secure=True, the 'Secure' flag is appended to both cookies.

    The CSRF token cookie AND the anonymous nonce cookie should contain 'Secure' when
    CSRFMiddleware is initialized with cookie_secure=True.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "testing")
    app = _make_app()
    # Use cookie_secure=True to trigger the `parts.append("Secure")` branches
    app.add_middleware(
        CSRFMiddleware,
        csrf_hmac_secret="",
        cookie_secure=True,  # Forces lines 431 and 452
        cookie_samesite="strict",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.get("/safe")
    # The CSRF Set-Cookie header should include 'Secure'
    set_cookie_headers = [
        v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"
    ]
    csrf_cookie = next(
        (h for h in set_cookie_headers if CSRF_COOKIE_NAME in h), None
    )
    assert csrf_cookie is not None, "CSRF cookie not set"
    assert "Secure" in csrf_cookie, f"Expected 'Secure' in CSRF cookie: {csrf_cookie!r}"


def test_extract_session_id_with_existing_session_id() -> None:
    """Lines 169→184: _extract_session_id returns existing session_id without generating anon nonce.

    When request.state already has a session_id (set by JWT middleware), the function
    should return it directly, skipping the anonymous nonce generation path.
    """
    from types import SimpleNamespace

    from app.core.csrf import _NEW_ANON_NONCE_STATE_KEY, _extract_session_id

    # Use a real SimpleNamespace so hasattr() works correctly (MagicMock auto-creates attrs).
    mock_state = SimpleNamespace(session_id="existing-session-abc123")

    class _FakeRequest:
        state = mock_state
        cookies: dict = {}

    session_id = _extract_session_id(_FakeRequest(), "dummy-cookie-token")  # type: ignore[arg-type]

    # Should return the existing session_id directly (branch at line 169 is False)
    assert session_id == "existing-session-abc123"
    # The NEW_ANON_NONCE_STATE_KEY should NOT be set (no new nonce generated)
    assert not hasattr(mock_state, _NEW_ANON_NONCE_STATE_KEY)
