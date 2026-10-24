import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.security import _mint_pure_jwt, decode_token
from app.core.config import settings

_ISSUER = "https://issuer.example/aud354"
_AUDIENCE = "aud354-test-audience"


def _configure_signing_keys(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    active_key = secrets.token_urlsafe(32)
    previous_key = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "algorithm", "HS256")
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        [f"active:{active_key}", f"previous:{previous_key}"],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "active")
    monkeypatch.setattr(settings, "jwt_issuer", _ISSUER)
    monkeypatch.setattr(settings, "jwt_audience", _AUDIENCE)
    return active_key, previous_key


def _signed_token(*, kid: str, key: str, issuer: str | None) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": "aud354-user",
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": f"aud354-{kid}-jti",
    }
    if issuer is not None:
        claims["iss"] = issuer
    return jwt.encode(claims, key, algorithm="HS256", headers={"kid": kid})


def test_decode_token_requires_issuer_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    active_key, _ = _configure_signing_keys(monkeypatch)
    token = _signed_token(kid="active", key=active_key, issuer=None)

    decoded = decode_token(token)
    assert decoded is None


def test_decode_token_rejects_foreign_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    active_key, _ = _configure_signing_keys(monkeypatch)
    token = _signed_token(
        kid="active", key=active_key, issuer="https://foreign.example/"
    )

    decoded = decode_token(token)
    assert decoded is None


def test_decode_token_rejects_missing_issuer_for_previous_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, previous_key = _configure_signing_keys(monkeypatch)
    token = _signed_token(kid="previous", key=previous_key, issuer=None)

    decoded = decode_token(token)
    assert decoded is None


def test_decode_token_accepts_expected_issuer_for_active_and_previous_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key, previous_key = _configure_signing_keys(monkeypatch)

    for kid, key in (("active", active_key), ("previous", previous_key)):
        token = _signed_token(kid=kid, key=key, issuer=_ISSUER)
        payload = decode_token(token)

        assert payload is not None
        assert payload["iss"] == _ISSUER
        assert payload["sub"] == "aud354-user"


def test_minted_token_uses_configured_issuer_and_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key, _ = _configure_signing_keys(monkeypatch)

    token = _mint_pure_jwt("aud354-user")
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        active_key,
        algorithms=["HS256"],
        audience=_AUDIENCE,
        issuer=_ISSUER,
        options={"require": ["iss"]},
    )

    assert header["kid"] == "active"
    assert payload["iss"] == _ISSUER
    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "aud354-user"
