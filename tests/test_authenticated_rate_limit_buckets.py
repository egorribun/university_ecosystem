"""AUD-164: verified identities separate traffic, never auth attack budgets.

Bucketing-only semantics: the rate-limit key is derived from a signature-checked
access token, but no revocation, session or account state is consulted. A token
that is still signature-valid after logout, or whose account was deactivated,
keeps its own user bucket until it expires. One actor holding N accounts gets N
buckets on non-auth routes. Login, register and password routes always use the
client IP bucket.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import cache
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from starlette.datastructures import Headers

from app.auth.security import _mint_pure_jwt
from app.core.config import settings
from app.core.ratelimit import RateLimitMiddleware, clear_memory_state
from app.core.ratelimit.fastapi import sensitive_route_limit
from app.core.ratelimit.policy import uses_ip_bucket
from app.core.ratelimit.utils import extract_user_id_for_ratelimit

PROTECTED_PATH = "/api/v1/news"
AUTH_PATH = "/api/v1/auth/login"
TRUSTED_PROXY = "198.51.100.9"
UNTRUSTED_PEER = "203.0.113.9"


@pytest.fixture(autouse=True)
def isolated_buckets(monkeypatch):
    clear_memory_state()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "trusted_proxies_list", [])
    yield
    clear_memory_state()


def _app(path, *, sensitive):
    app = FastAPI()
    dependencies = (
        [Depends(sensitive_route_limit(limit=2, window_sec=60))] if sensitive else []
    )
    if not sensitive:
        app.add_middleware(
            RateLimitMiddleware, storage_backend="memory", limit=2, window_seconds=60
        )

    @app.post(path, dependencies=dependencies)
    async def limited():
        return {"ok": True}

    return app


@asynccontextmanager
async def _client(app, peer: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=(peer, 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _signed(claims=None, *, kid=None, key=None):
    """Sign a token with the active key unless overridden. Test-only helper."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid4()),
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
        "is_active": True,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid4()),
        **(claims or {}),
    }
    return jwt.encode(
        payload,
        key if key is not None else settings.jwt_signing_active_secret,
        algorithm=settings.algorithm,
        headers={"kid": kid if kid is not None else settings.jwt_signing_active_kid},
    )


@cache
def _foreign_key() -> str:
    """A signing key that is not in the registry (same algorithm family)."""
    if not settings.algorithm.startswith("RS"):
        return "foreign-secret-" + "x" * 48
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Verified users keep independent budgets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize("credential", ["bearer", "cookie"])
async def test_verified_users_have_independent_budgets(sensitive, credential):
    path = PROTECTED_PATH
    subject = uuid4()
    first = _mint_pure_jwt(subject)
    rotated = _mint_pure_jwt(subject)
    second = _mint_pure_jwt(uuid4())
    app = _app(path, sensitive=sensitive)
    async with _client(app, "198.51.100.9") as client:
        statuses = []
        for value in (first, first, rotated, second, second, second):
            headers = (
                {"Authorization": f"Bearer {value}"}
                if credential == "bearer"
                else {"Cookie": f"access_token_v2={value}"}
            )
            response = await client.post(path, headers=headers)
            statuses.append(response.status_code)
    assert statuses == [200, 200, 429, 200, 200, 429]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_same_user_from_two_ips_shares_one_bucket(sensitive):
    app = _app(PROTECTED_PATH, sensitive=sensitive)
    token = _mint_pure_jwt(uuid4())
    statuses = []
    for peer in ("198.51.100.9", "198.51.100.9", "203.0.113.8"):
        async with _client(app, peer) as client:
            statuses.append(
                (await client.post(PROTECTED_PATH, headers=_bearer(token))).status_code
            )
    assert statuses == [200, 200, 429]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_valid_token_is_not_ip_bucketed(sensitive):
    """Control case: proves the anonymous and token budgets are distinct here."""
    app = _app(PROTECTED_PATH, sensitive=sensitive)
    token = _mint_pure_jwt(uuid4())
    async with _client(app, "198.51.100.9") as client:
        statuses = [
            (await client.post(PROTECTED_PATH, headers=_bearer(token))).status_code,
            (await client.post(PROTECTED_PATH, headers=_bearer(token))).status_code,
            (await client.post(PROTECTED_PATH)).status_code,
        ]
    assert statuses == [200, 200, 200]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_revocation_is_not_consulted_for_bucketing(sensitive):
    """Accepted residual: a signature-valid token whose jti is in no session store
    (logged out, revoked or never registered) still gets its own user bucket
    until it expires. Bucketing grants no access, so this is not an authz gap."""
    app = _app(PROTECTED_PATH, sensitive=sensitive)
    unregistered = _signed()
    async with _client(app, "198.51.100.9") as client:
        statuses = [
            (
                await client.post(PROTECTED_PATH, headers=_bearer(unregistered))
            ).status_code
            for _ in range(3)
        ]
        anonymous = (await client.post(PROTECTED_PATH)).status_code
    assert statuses == [200, 200, 429]
    assert anonymous == 200


# ---------------------------------------------------------------------------
# Credentials that are not a usable access token fall back to the IP bucket
# ---------------------------------------------------------------------------

_EXPIRED = {"exp": datetime.now(UTC) - timedelta(days=1)}


def _unusable_credentials():
    return [
        pytest.param(lambda: _bearer(_signed(_EXPIRED)), id="expired"),
        pytest.param(
            lambda: _bearer(_signed({"aud": "other-audience"})), id="wrong-aud"
        ),
        pytest.param(lambda: _bearer(_signed({"iss": "other-issuer"})), id="wrong-iss"),
        pytest.param(
            lambda: _bearer(_signed(kid="unknown-kid-for-test")), id="unknown-kid"
        ),
        pytest.param(
            lambda: _bearer(_signed(key=_foreign_key())), id="wrong-signing-key"
        ),
        pytest.param(lambda: _bearer(_signed({"type": "refresh"})), id="type-refresh"),
        pytest.param(lambda: _bearer(_signed({"typ": "refresh"})), id="typ-refresh"),
        pytest.param(
            lambda: _bearer(_signed({"token_type": "mfa"})), id="token-type-mfa"
        ),
        pytest.param(
            lambda: _bearer(_signed({"token_use": "step_up"})), id="token-use-step-up"
        ),
        pytest.param(
            lambda: _bearer(_signed({"purpose": "mfa_step_up"})), id="purpose-step-up"
        ),
        pytest.param(
            lambda: _bearer(_signed({"sub": "not-a-uuid"})), id="sub-not-uuid"
        ),
        pytest.param(lambda: _bearer(_signed({"sub": 7})), id="sub-integer"),
        pytest.param(
            lambda: _bearer(_signed({"sub": str(uuid4()).upper()})),
            id="sub-uppercase-uuid",
        ),
        pytest.param(
            lambda: _bearer(_signed({"sub": str(uuid4()).replace("-", "")})),
            id="sub-hyphenless-uuid",
        ),
        pytest.param(
            lambda: _bearer(_signed({"sub": f"{{{uuid4()}}}"})), id="sub-braced-uuid"
        ),
        pytest.param(
            lambda: {"Authorization": f"Basic {_signed()}"}, id="basic-scheme"
        ),
        pytest.param(
            lambda: {"Authorization": f"Token {_signed()}"}, id="token-scheme"
        ),
        pytest.param(lambda: {"Authorization": "Bearer"}, id="bearer-without-token"),
        pytest.param(lambda: {"Authorization": "Bearer    "}, id="bearer-blank-token"),
        pytest.param(lambda: _bearer("abc.def.ghi"), id="bearer-not-a-jwt"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize("make_headers", _unusable_credentials())
async def test_unusable_credentials_share_the_ip_budget(sensitive, make_headers):
    app = _app(PROTECTED_PATH, sensitive=sensitive)
    async with _client(app, "198.51.100.9") as client:
        statuses = [
            (await client.post(PROTECTED_PATH, headers=make_headers())).status_code,
            (await client.post(PROTECTED_PATH)).status_code,
            (await client.post(PROTECTED_PATH, headers=make_headers())).status_code,
        ]
    assert statuses == [200, 200, 429]


class _FakeRequest:
    def __init__(self, raw_headers: dict[str, str]) -> None:
        self.headers = Headers(raw_headers)
        cookie_header = raw_headers.get("Cookie", "")
        self.cookies = dict(
            part.split("=", 1) for part in cookie_header.split("; ") if "=" in part
        )


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-credentials"),
        pytest.param({"Authorization": "Bearer"}, id="bearer-without-token"),
        pytest.param({"Authorization": "Basic abc"}, id="basic-scheme"),
        pytest.param({"Authorization": "Bearer abc.def.ghi"}, id="bearer-not-a-jwt"),
        pytest.param({"Cookie": "access_token_v2="}, id="empty-cookie"),
    ],
)
def test_extract_user_id_returns_none_for_unusable_credentials(headers):
    assert extract_user_id_for_ratelimit(_FakeRequest(headers)) is None


def test_extract_user_id_returns_canonical_sub_for_access_token():
    subject = uuid4()
    request = _FakeRequest(
        {"Authorization": f"Bearer {_signed({'sub': str(subject)})}"}
    )
    assert extract_user_id_for_ratelimit(request) == str(subject)


# ---------------------------------------------------------------------------
# Forwarded client addresses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_untrusted_peer_forwarded_headers_are_ignored(sensitive, monkeypatch):
    """With trusted proxies configured, a non-proxy peer cannot choose its IP key."""
    monkeypatch.setattr(settings, "trusted_proxies_list", ["198.51.100.0/24"])
    app = _app(AUTH_PATH, sensitive=sensitive)
    statuses = []
    async with _client(app, UNTRUSTED_PEER) as client:
        for forged in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
            headers = {"X-Forwarded-For": forged, "Forwarded": f"for={forged}"}
            statuses.append((await client.post(AUTH_PATH, headers=headers)).status_code)
    assert statuses == [200, 200, 429]


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_trusted_proxy_forwarded_client_gets_its_own_bucket(
    sensitive, monkeypatch
):
    monkeypatch.setattr(settings, "trusted_proxies_list", ["198.51.100.0/24"])
    app = _app(AUTH_PATH, sensitive=sensitive)
    async with _client(app, TRUSTED_PROXY) as client:
        statuses = [
            (
                await client.post(AUTH_PATH, headers={"X-Forwarded-For": "203.0.113.5"})
            ).status_code
            for _ in range(3)
        ]
        other_client = (
            await client.post(AUTH_PATH, headers={"X-Forwarded-For": "203.0.113.6"})
        ).status_code
    assert statuses == [200, 200, 429]
    assert other_client == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_valid_token_cannot_move_auth_route_off_ip_bucket(sensitive, monkeypatch):
    """Auth routes ignore tokens entirely: a valid token cannot escape the IP key."""
    monkeypatch.setattr(settings, "trusted_proxies_list", ["198.51.100.0/24"])
    app = _app(AUTH_PATH, sensitive=sensitive)
    statuses = []
    async with _client(app, TRUSTED_PROXY) as client:
        for _ in range(3):
            token = _mint_pure_jwt(uuid4())
            response = await client.post(
                AUTH_PATH,
                headers={"X-Forwarded-For": "203.0.113.5", **_bearer(token)},
            )
            statuses.append(response.status_code)
    assert statuses == [200, 200, 429]


# ---------------------------------------------------------------------------
# Route policy boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/auth/login", True),
        ("/api/v1/auth/login/", True),
        ("/api/v1/auth/login/json", True),
        ("/api/v1/auth/LOGIN", True),
        ("/api/v1/auth/loginx", False),
        ("/api/v1/auth/login-helper", False),
        ("/api/v1/auth/register", True),
        ("/api/v1/auth/register/", True),
        ("/api/v1/auth/registration", False),
        ("/api/v1/password", True),
        ("/api/v1/password/", True),
        ("/api/v1/password/forgot", True),
        ("/api/v1/password/reset", True),
        ("/api/v1/PASSWORD/reset", True),
        ("/api/v1/passwords", False),
        ("/api/v1/passwords/forgot", False),
        ("/api/v1/auth/sessions", False),
        ("/api/v1/auth/mfa/verify", False),
        ("/api/v1/news", False),
        ("/", False),
        ("", False),
    ],
)
def test_uses_ip_bucket_respects_segment_boundaries(path, expected):
    assert uses_ip_bucket(path) is expected
