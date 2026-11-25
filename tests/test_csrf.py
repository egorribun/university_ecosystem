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
from fastapi import FastAPI, Request

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

    def test_rejects_a_nonce_that_borrows_the_session_prefix(self) -> None:
        """A fixed nonce length keeps ``nonce + session_id`` unambiguous."""
        token = _build_signed_token("abc", _TEST_SECRET)
        nonce, mac = token.split(".", 1)
        assert len(nonce) == 43
        assert _verify_signed_token(f"{nonce}a.{mac}", "bc", _TEST_SECRET) is False
        assert _verify_signed_token(f"{nonce[:-1]}.{mac}", "abc", _TEST_SECRET) is False

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
    assert response.headers.get("x-csrf-rejected") == "1"
    assert response.headers.get_list("cache-control") == ["private, no-store"]


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
@pytest.mark.parametrize(
    "cookie_name", ["access_token_v2", "access_token", "session_id"]
)
async def test_bearer_with_auth_cookie_still_validated(cookie_name: str) -> None:
    """Bearer + access_token cookie → CSRF must still be enforced."""
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        client.cookies.set(cookie_name, "logged-in-cookie")
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

    Line 452 (_build_anon_nonce_cookie Secure append) requires SIGNED mode, because
    _extract_session_id is only called during response when self._signed=True (line 392).
    """
    app = _make_app()
    # Use cookie_secure=True AND signed mode to trigger both Secure branches
    app.add_middleware(
        CSRFMiddleware,
        csrf_hmac_secret="x"
        * 32,  # Signed mode so _extract_session_id runs (lines 392-393)
        cookie_secure=True,  # Forces lines 431 (CSRF token) and 452 (anon nonce)
        cookie_samesite="strict",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        response = await client.get("/safe")
    # Both CSRF and anon nonce Set-Cookie headers should include 'Secure'
    set_cookie_headers = [
        v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"
    ]
    csrf_cookie = next((h for h in set_cookie_headers if CSRF_COOKIE_NAME in h), None)
    assert csrf_cookie is not None, "CSRF cookie not set"
    assert "Secure" in csrf_cookie, f"Expected 'Secure' in CSRF cookie: {csrf_cookie!r}"

    # Also verify the anon nonce cookie has 'Secure' flag (line 452 in _build_anon_nonce_cookie)
    anon_nonce_cookie = next(
        (h for h in set_cookie_headers if _ANON_NONCE_COOKIE_NAME in h), None
    )
    assert anon_nonce_cookie is not None, (
        f"Anon nonce cookie not set. Cookies: {set_cookie_headers}"
    )
    assert "Secure" in anon_nonce_cookie, (
        f"Expected 'Secure' in anon nonce cookie: {anon_nonce_cookie!r}"
    )


async def test_non_http_scope_bypasses() -> None:
    """Non-HTTP scopes (like websocket or lifespan) bypass CSRF middleware."""
    from unittest.mock import AsyncMock

    app = AsyncMock()
    middleware = CSRFMiddleware(app, csrf_hmac_secret="a" * 32)
    scope = {"type": "websocket"}
    receive = AsyncMock()
    send = AsyncMock()
    await middleware(scope, receive, send)
    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_secure_cookies_flag() -> None:
    """CSRF and anon nonce cookies get the Secure flag when cookie_secure=True."""
    app = _make_app()
    app.add_middleware(CSRFMiddleware, csrf_hmac_secret="a" * 32, cookie_secure=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        response = await client.get("/safe")
        set_cookies = response.headers.get_list("set-cookie")
        assert len(set_cookies) >= 2
        csrf_cookie_header = next(c for c in set_cookies if CSRF_COOKIE_NAME in c)
        anon_cookie_header = next(
            c for c in set_cookies if _ANON_NONCE_COOKIE_NAME in c
        )
        assert "Secure" in csrf_cookie_header
        assert "Secure" in anon_cookie_header


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "cookie_max_age",
        "cookie_secure",
        "cookie_samesite",
        "base_url",
        "expected_max_age",
    ),
    [
        pytest.param(
            None, True, "strict", "https://testserver", 86400, id="constructor-default"
        ),
        pytest.param(
            3600,
            True,
            "strict",
            "https://testserver",
            3600,
            id="configured-access-token-lifetime",
        ),
        pytest.param(
            73,
            False,
            "lax",
            "http://testserver",
            73,
            id="nondefault-lifetime-and-cookie-policy",
        ),
    ],
)
async def test_csrf_rotation_renews_anonymous_nonce_lifetime(
    cookie_max_age: int | None,
    cookie_secure: bool,
    cookie_samesite: str,
    base_url: str,
    expected_max_age: int,
) -> None:
    """A rotated CSRF token keeps its anonymous HMAC binding cookie aligned."""

    app = _make_app()

    @app.post("/rotate")
    async def _rotate(request: Request) -> dict[str, str]:
        signal_csrf_rotation(request)
        return {"ok": "yes"}

    middleware_options: dict[str, Any] = {
        "csrf_hmac_secret": "x" * 32,
        "cookie_secure": cookie_secure,
        "cookie_samesite": cookie_samesite,
    }
    if cookie_max_age is not None:
        middleware_options["cookie_max_age"] = cookie_max_age
    app.add_middleware(CSRFMiddleware, **middleware_options)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        initial = await client.get("/safe")
        assert initial.status_code == 200
        original_nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        original_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert original_nonce is not None
        assert _ANON_NONCE_RE.fullmatch(original_nonce)
        assert original_token is not None

        rotated = await client.post(
            "/rotate", headers={CSRF_HEADER_NAME: original_token}
        )
        assert rotated.status_code == 200
        rotated_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert rotated_token is not None
        assert rotated_token != original_token
        assert client.cookies.get(_ANON_NONCE_COOKIE_NAME) == original_nonce

        set_cookie_headers = rotated.headers.get_list("set-cookie")

        def cookie_header(name: str) -> str:
            matches = [
                header
                for header in set_cookie_headers
                if header.partition("=")[0].lower() == name.lower()
            ]
            assert len(matches) == 1, (name, set_cookie_headers)
            return matches[0]

        def attributes(header: str) -> dict[str, str | None]:
            parsed: dict[str, str | None] = {}
            for item in header.split(";")[1:]:
                key, separator, value = item.strip().partition("=")
                parsed[key.lower()] = value if separator else None
            return parsed

        csrf_header = cookie_header(CSRF_COOKIE_NAME)
        nonce_header = cookie_header(_ANON_NONCE_COOKIE_NAME)
        nonce_set_value = nonce_header.partition(";")[0].split("=", 1)[1]
        assert nonce_set_value == original_nonce

        csrf_attributes = attributes(csrf_header)
        nonce_attributes = attributes(nonce_header)
        for cookie_attributes in (csrf_attributes, nonce_attributes):
            assert cookie_attributes.get("path") == "/"
            assert cookie_attributes.get("max-age") == str(expected_max_age)
            assert cookie_attributes.get("samesite", "").lower() == cookie_samesite
            assert ("secure" in cookie_attributes) is cookie_secure
            assert "domain" not in cookie_attributes
        assert "httponly" not in csrf_attributes
        assert "httponly" in nonce_attributes

        next_action = await client.post(
            "/mut", headers={CSRF_HEADER_NAME: rotated_token}
        )
        assert next_action.status_code == 200


@pytest.mark.asyncio
async def test_csrf_unrotated_valid_request_does_not_reissue_cookies() -> None:
    """A valid unrotated mutation keeps both cookies without extra Set-Cookie."""
    app = _make_app()
    app.add_middleware(
        CSRFMiddleware,
        csrf_hmac_secret="x" * 32,
        cookie_secure=False,
        cookie_samesite="lax",
        cookie_max_age=420,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        initial = await client.get("/safe")
        nonce_before = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        token_before = client.cookies.get(CSRF_COOKIE_NAME)
        assert initial.status_code == 200
        assert nonce_before is not None
        assert token_before is not None

        response = await client.post("/mut", headers={CSRF_HEADER_NAME: token_before})
        assert response.status_code == 200
        assert response.headers.get_list("set-cookie") == []
        assert client.cookies.get(_ANON_NONCE_COOKIE_NAME) == nonce_before
        assert client.cookies.get(CSRF_COOKIE_NAME) == token_before


@pytest.mark.asyncio
async def test_first_visit_anonymous_nonce_lives_as_long_as_csrf_cookie() -> None:
    """AUD-001: the anonymous nonce must not expire before the CSRF cookie it binds.

    A one-hour nonce left a day-long CSRF cookie unbound after an hour, so the
    next unrotated mutation failed the HMAC check with 403.
    """
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/safe")

    def max_age(name: str) -> str:
        header = next(
            h
            for h in response.headers.get_list("set-cookie")
            if h.partition("=")[0].lower() == name.lower()
        )
        attributes = {
            item.strip().partition("=")[0].lower(): item.strip().partition("=")[2]
            for item in header.split(";")[1:]
        }
        return attributes["max-age"]

    assert max_age(_ANON_NONCE_COOKIE_NAME) == max_age(CSRF_COOKIE_NAME)


@pytest.fixture
def signed_application(app: FastAPI) -> FastAPI:
    """Exercise the real routes with a test-specific signed CSRF middleware."""
    from copy import copy

    from starlette.middleware import Middleware

    signed_app = copy(app)
    signed_app.middleware_stack = None
    signed_app.user_middleware = [
        Middleware(
            item.cls,
            *item.args,
            **{**item.kwargs, "csrf_hmac_secret": "x" * 32},
        )
        if item.cls is CSRFMiddleware
        else item
        for item in app.user_middleware
    ]
    return signed_app


@pytest.mark.asyncio
async def test_login_issues_csrf_bound_to_the_new_session(
    signed_application: FastAPI, user_factory: Any
) -> None:
    """The login response binds the new cookie before its JWT is in a request."""
    from app.auth.security import decode_token, get_password_hash

    password = secrets.token_urlsafe(20) + "aA1!"
    user = await user_factory(hashed_password=await get_password_hash(password))
    transport = httpx.ASGITransport(app=signed_application)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        initial = await client.get("/api/v1/auth/csrf-cookie")
        assert initial.status_code == 200
        anonymous_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert anonymous_token is not None

        login = await client.post(
            "/api/v1/auth/login/json",
            headers={CSRF_HEADER_NAME: anonymous_token},
            json={"email": user.email, "password": password},
        )
        assert login.status_code == 200
        access_token = client.cookies.get("access_token_v2")
        authenticated_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert access_token is not None and authenticated_token is not None
        payload = decode_token(access_token)
        assert payload is not None
        assert authenticated_token != anonymous_token
        assert _verify_signed_token(authenticated_token, payload["jti"], b"x" * 32)

        # A subsequent sign-in issues a different session even when the
        # anonymous nonce cookie is no longer present.
        client.cookies.delete(_ANON_NONCE_COOKIE_NAME)
        second_login = await client.post(
            "/api/v1/auth/login/json",
            headers={CSRF_HEADER_NAME: authenticated_token},
            json={"email": user.email, "password": password},
        )
        assert second_login.status_code == 200
        new_access_token = client.cookies.get("access_token_v2")
        new_csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert new_access_token is not None and new_csrf_token is not None
        new_payload = decode_token(new_access_token)
        assert new_payload is not None
        assert new_payload["jti"] != payload["jti"]
        assert _verify_signed_token(new_csrf_token, new_payload["jti"], b"x" * 32)

        logout = await client.post(
            "/api/v1/auth/logout",
            headers={CSRF_HEADER_NAME: new_csrf_token},
        )
        assert logout.status_code == 200
        next_token = client.cookies.get(CSRF_COOKIE_NAME)
        nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        assert next_token is not None and nonce is not None
        assert _verify_signed_token(next_token, f"anon:{nonce}", b"x" * 32)

        login_again = await client.post(
            "/api/v1/auth/login/json",
            headers={CSRF_HEADER_NAME: next_token},
            json={"email": user.email, "password": password},
        )
        assert login_again.status_code == 200


@pytest.mark.asyncio
async def test_safe_request_renews_csrf_after_session_ends(
    signed_application: FastAPI, user_factory: Any
) -> None:
    """An expired browser session can obtain a fresh anonymous CSRF cookie."""
    from app.auth.security import get_password_hash

    password = secrets.token_urlsafe(20) + "aA1!"
    user = await user_factory(hashed_password=await get_password_hash(password))
    transport = httpx.ASGITransport(app=signed_application)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        await client.get("/api/v1/auth/csrf-cookie")
        initial = client.cookies.get(CSRF_COOKIE_NAME)
        assert initial is not None
        login = await client.post(
            "/api/v1/auth/login/json",
            headers={CSRF_HEADER_NAME: initial},
            json={"email": user.email, "password": password},
        )
        assert login.status_code == 200
        authenticated_token = client.cookies.get(CSRF_COOKIE_NAME)
        client.cookies.delete("access_token_v2")

        refreshed = await client.get("/api/v1/auth/csrf-cookie")
        assert refreshed.status_code == 200
        renewed_token = client.cookies.get(CSRF_COOKIE_NAME)
        nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        assert renewed_token is not None and nonce is not None
        assert renewed_token != authenticated_token
        assert _verify_signed_token(renewed_token, f"anon:{nonce}", b"x" * 32)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mint_options",
    [{"expires_minutes": -1}, {"extra_claims": {"jti": ""}}],
    ids=["expired-session", "empty-session-id"],
)
async def test_unusable_access_cookie_keeps_anonymous_csrf_flow(
    mint_options: dict[str, Any],
) -> None:
    """An unusable access cookie does not prevent anonymous CSRF bootstrap."""
    from app.auth.security import _mint_pure_jwt

    access_token = _mint_pure_jwt("test-user", **mint_options)
    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        client.cookies.set("access_token_v2", access_token)
        initial = await client.get("/safe")
        assert initial.status_code == 200
        nonce = client.cookies.get(_ANON_NONCE_COOKIE_NAME)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert nonce is not None and csrf_token is not None
        assert _verify_signed_token(csrf_token, f"anon:{nonce}", b"x" * 32)
        response = await client.post("/mut", headers={CSRF_HEADER_NAME: csrf_token})
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream_public_cache", [False, True])
async def test_csrf_cookie_response_is_not_publicly_cacheable(
    upstream_public_cache: bool,
) -> None:
    """Static cache policy must not expose a newly issued session-bound cookie."""
    from fastapi.responses import Response

    from app.auth.security import _mint_pure_jwt, decode_token
    from app.core.middleware.response_hardening import http_response_hardening

    app = FastAPI()

    @app.get("/static/example")
    async def static_example() -> Response:
        headers = (
            {"Cache-Control": "public, max-age=86400"}
            if upstream_public_cache
            else None
        )
        return Response(content=b"example", headers=headers)

    app.add_middleware(CSRFMiddleware, csrf_hmac_secret="x" * 32, cookie_secure=False)
    app.middleware("http")(http_response_hardening)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        access_token = _mint_pure_jwt("test-user")
        payload = decode_token(access_token)
        assert payload is not None
        client.cookies.set("access_token_v2", access_token)

        initial = await client.get("/static/example")
        assert initial.status_code == 200
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert csrf_token is not None
        assert _verify_signed_token(csrf_token, payload["jti"], b"x" * 32)
        assert initial.headers.get_list("cache-control") == ["private, no-store"]

        subsequent = await client.get("/static/example")
        assert subsequent.headers.get("cache-control") == "public, max-age=86400"
        assert subsequent.headers.get_list("set-cookie") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_missing_csrf_proof_has_pre_handler_marker(locale: str) -> None:
    from app.core.localization import translate

    app = _wrap(_make_app())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post("/mut", headers={"Accept-Language": locale})

    assert response.status_code == 403
    assert response.headers.get("x-csrf-rejected") == "1"
    assert response.headers.get_list("cache-control") == ["private, no-store"]
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == translate("errors.csrf.mismatch", locale=locale)


@pytest.mark.asyncio
async def test_stale_header_has_pre_handler_marker() -> None:
    app = _make_app()
    mutations: list[str] = []

    @app.post("/rotate-marker-test")
    async def rotate(request: Request) -> dict[str, str]:
        signal_csrf_rotation(request)
        return {"ok": "yes"}

    @app.post("/tracked-marker-test")
    async def tracked() -> dict[str, str]:
        mutations.append("called")
        return {"ok": "yes"}

    _wrap(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.get("/safe")
        initial_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert initial_token is not None
        rotated = await client.post(
            "/rotate-marker-test", headers={CSRF_HEADER_NAME: initial_token}
        )
        assert rotated.status_code == 200
        assert "x-csrf-rejected" not in rotated.headers
        assert client.cookies.get(CSRF_COOKIE_NAME) != initial_token

        response = await client.post(
            "/tracked-marker-test", headers={CSRF_HEADER_NAME: initial_token}
        )

    assert response.status_code == 403
    assert response.headers.get("x-csrf-rejected") == "1"
    assert response.headers.get_list("cache-control") == ["private, no-store"]
    assert mutations == []


@pytest.mark.asyncio
async def test_stale_session_binding_rejection_precedes_logout(
    signed_application: FastAPI, user_factory: Any
) -> None:
    """An anonymous token from before login cannot authorize logout."""
    from app.auth.security import get_password_hash

    password = secrets.token_urlsafe(20) + "aA1!"
    user = await user_factory(hashed_password=await get_password_hash(password))
    transport = httpx.ASGITransport(app=signed_application)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        await client.get("/api/v1/auth/csrf-cookie")
        anonymous_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert anonymous_token is not None
        login = await client.post(
            "/api/v1/auth/login/json",
            headers={CSRF_HEADER_NAME: anonymous_token},
            json={"email": user.email, "password": password},
        )
        assert login.status_code == 200
        assert client.cookies.get(CSRF_COOKIE_NAME) != anonymous_token

        # Model the old anonymous response arriving after the login response.
        csrf_cookie = next(
            cookie for cookie in client.cookies.jar if cookie.name == CSRF_COOKIE_NAME
        )
        csrf_cookie.value = anonymous_token
        response = await client.post(
            "/api/v1/auth/logout", headers={CSRF_HEADER_NAME: anonymous_token}
        )
        assert response.status_code == 403
        assert response.headers.get("x-csrf-rejected") == "1"
        assert response.headers.get_list("cache-control") == ["private, no-store"]
        assert (await client.get("/api/v1/users/me")).status_code == 200


@pytest.mark.asyncio
async def test_handler_forbidden_response_has_no_csrf_marker() -> None:
    from fastapi import HTTPException

    app = _make_app()

    @app.post("/forbidden-marker-test")
    async def forbidden() -> None:
        raise HTTPException(status_code=403, detail="operation denied")

    _wrap(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.get("/safe")
        token = client.cookies.get(CSRF_COOKIE_NAME)
        assert token is not None
        response = await client.post(
            "/forbidden-marker-test", headers={CSRF_HEADER_NAME: token}
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "operation denied"
    assert "x-csrf-rejected" not in response.headers


@pytest.mark.asyncio
async def test_csrf_marker_is_private_through_outer_response_hardening() -> None:
    from app.core.middleware.response_hardening import http_response_hardening

    app = _wrap(_make_app())
    app.middleware("http")(http_response_hardening)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/static/example")

    assert response.status_code == 403
    assert response.headers.get("x-csrf-rejected") == "1"
    assert response.headers.get_list("cache-control") == ["private, no-store"]


@pytest.mark.asyncio
async def test_csrf_bootstrap_is_private_without_cookie_rotation(
    signed_application: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=signed_application)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://testserver"
    ) as client:
        initial = await client.get("/api/v1/auth/csrf-cookie")
        assert initial.status_code == 200
        assert initial.headers.get_list("cache-control") == ["private, no-store"]
        assert initial.cookies.get(CSRF_COOKIE_NAME) is not None

        subsequent = await client.get("/api/v1/auth/csrf-cookie")
        assert subsequent.status_code == 200
        assert subsequent.headers.get_list("set-cookie") == []
        assert subsequent.headers.get_list("cache-control") == ["private, no-store"]
        assert "x-csrf-rejected" not in subsequent.headers
