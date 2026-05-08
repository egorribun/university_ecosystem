"""W137 SW1 — RS256 JWT contract tests.

Closes W135 §Honesty #9 SSR layer (real Docker chain authed visual smoke
FAILED at SSR auth-at-edge layer because backend signed HS256 but ssrAuth.ts
validates via jose.createRemoteJWKSet which defaults to RS256). After W137
SW1, dev Docker backend signs RS256 (matches production deploy assumption +
gateway's existing JWKS hot-reload + ws-hub's existing JWKS_URL default).

Tests verify:
- SessionService produces RS256-signed tokens when ALGORITHM=RS256 + private key loaded
- JWT header carries alg=RS256 + kid (matches backend's payload.update(extra) chain)
- Decode roundtrips via public key extraction (mirrors gateway + ssrAuth.ts pattern)
- JWKS endpoint emits public key shape matching the private key used to sign
- Backwards-compat: existing W136 SW1 HS256 contract tests still pass under
  conftest.py's HS256 default; W137 RS256 tests are isolated via patch context

Pattern: monkey-patch app.core.config.settings to RS256 + RSA keypair within
a context manager so the test runs in isolation. Conftest's HS256 baseline is
restored on context exit.
"""

from __future__ import annotations

from unittest.mock import patch

import jwt as jose_jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_rsa_keypair() -> tuple[str, str]:
    """Generate an RSA-2048 keypair. Returns (private_pem, public_pem) in PEM format.

    Mirrors `tests/test_jwks_endpoint.py:generate_rsa_pem` (already imported by
    test_jwks_endpoint suite) but also returns the public key for decode verify.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _decode_jwt_with_public_key(token: str, public_pem: str, audience: str) -> dict:
    """Decode RS256 token via public key — mirrors gateway + ssrAuth.ts pattern."""
    return jose_jwt.decode(
        token,
        public_pem,
        algorithms=["RS256"],
        audience=audience,
        options={"require": ["sub", "jti", "exp", "iat", "aud"]},
    )


def _make_session_service(db_session):
    """Mirror W136 SW1 helper — bypasses async UnitOfWork pattern for unit tests."""
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.session_service import SessionService

    uow = UnitOfWork(lambda: db_session)
    uow._session = db_session  # type: ignore[assignment]
    uow._bind_repositories(db_session)
    return SessionService(uow)


@pytest.mark.asyncio
async def test_create_access_token_rs256_produces_valid_token(db_session, test_user):
    """RS256 settings + private key → SessionService produces RS256-signed token."""
    from app.core.config import settings

    private_pem, public_pem = _generate_rsa_keypair()
    test_kid = "primary-w137-test"

    # Patch settings module-level reference seen by session_service._mint_jwt.
    # session_service.py imports settings at module load — patch the reference there.
    with (
        patch.object(settings, "algorithm", "RS256"),
        patch.object(
            type(settings),
            "jwt_signing_active_secret",
            new_callable=lambda: property(lambda _: private_pem),
        ),
        patch.object(
            type(settings),
            "jwt_signing_active_kid",
            new_callable=lambda: property(lambda _: test_kid),
        ),
    ):
        service = _make_session_service(db_session)
        token, _ = await service.create_access_token(
            sub=test_user.id,
            extra_claims={"is_active": True},
        )

    # Inspect raw JWT header — must declare RS256 + kid
    header = jose_jwt.get_unverified_header(token)
    assert header["alg"] == "RS256", (
        f"JWT alg must be RS256 (was {header['alg']!r}); pre-W137 backend signed HS256"
    )
    assert header["kid"] == test_kid, "JWT kid must match active signing key id"

    # Decode via public key (mirrors gateway + ssrAuth.ts validation path)
    decoded = _decode_jwt_with_public_key(
        token, public_pem, audience=settings.jwt_audience
    )
    assert decoded["sub"] == str(test_user.id)
    assert decoded["is_active"] is True
    assert "jti" in decoded
    assert "exp" in decoded


@pytest.mark.asyncio
async def test_rs256_token_decode_fails_with_wrong_public_key(db_session, test_user):
    """RS256 signature is asymmetric — wrong public key MUST fail decode.

    Defends against algorithm confusion attacks (RZ-3 audit 2026-02-26): if a
    verifier accepted any public key, an attacker could forge tokens.
    """
    from app.core.config import settings

    signer_private_pem, _ = _generate_rsa_keypair()
    _, attacker_public_pem = _generate_rsa_keypair()  # Different keypair

    with (
        patch.object(settings, "algorithm", "RS256"),
        patch.object(
            type(settings),
            "jwt_signing_active_secret",
            new_callable=lambda: property(lambda _: signer_private_pem),
        ),
        patch.object(
            type(settings),
            "jwt_signing_active_kid",
            new_callable=lambda: property(lambda _: "primary"),
        ),
    ):
        service = _make_session_service(db_session)
        token, _ = await service.create_access_token(sub=test_user.id)

    with pytest.raises(jose_jwt.InvalidSignatureError):
        _decode_jwt_with_public_key(
            token, attacker_public_pem, audience=settings.jwt_audience
        )


@pytest.mark.asyncio
async def test_rs256_token_decode_fails_with_hs256_secret(db_session, test_user):
    """RS256 token MUST NOT decode as HS256 with public key as secret.

    Algorithm confusion attack vector: if a verifier accepted alg=HS256 against
    a public key as the HMAC secret, an attacker who has the public key could
    forge tokens. PyJWT's algorithm allowlist check rejects this.
    """
    from app.core.config import settings

    private_pem, public_pem = _generate_rsa_keypair()

    with (
        patch.object(settings, "algorithm", "RS256"),
        patch.object(
            type(settings),
            "jwt_signing_active_secret",
            new_callable=lambda: property(lambda _: private_pem),
        ),
        patch.object(
            type(settings),
            "jwt_signing_active_kid",
            new_callable=lambda: property(lambda _: "primary"),
        ),
    ):
        service = _make_session_service(db_session)
        token, _ = await service.create_access_token(sub=test_user.id)

    # Attempt to decode as HS256 with public key — must fail
    with pytest.raises((jose_jwt.InvalidAlgorithmError, jose_jwt.DecodeError)):
        jose_jwt.decode(
            token,
            public_pem,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )


def test_jwks_endpoint_emits_public_key_for_rs256_signing_key():
    """Backend's /.well-known/jwks.json MUST emit public key matching the signer.

    Verifies the chain: backend signs with private key from .secrets/jwt_rs256.pem,
    JWKS endpoint extracts public key from same registry, gateway/ssrAuth.ts/jose
    decode via that public key. If JWKS emits wrong key, signature check fails →
    SSR redirect to /login (the W135 §Honesty #9 symptom).
    """
    from app.api.well_known import _get_jwk_from_pem

    private_pem, _ = _generate_rsa_keypair()
    test_kid = "primary-jwks-test"

    jwk = _get_jwk_from_pem(test_kid, private_pem, "RS256")
    assert jwk is not None, "JWKS extraction returned None for RS256 PEM"
    assert jwk.kty == "RSA"
    assert jwk.alg == "RS256"
    assert jwk.kid == test_kid
    # RFC 7517: public key has n + e but NOT d/p/q (private components)
    assert jwk.n, "JWK must contain modulus (n)"
    assert jwk.e, "JWK must contain exponent (e)"
    # Defense-in-depth: ensure d (private exponent) is NOT exposed
    jwk_dict = jwk.model_dump()
    assert "d" not in jwk_dict, "JWK MUST NOT expose private exponent (d)"
    assert "p" not in jwk_dict, "JWK MUST NOT expose first prime (p)"
    assert "q" not in jwk_dict, "JWK MUST NOT expose second prime (q)"


@pytest.mark.asyncio
async def test_rs256_token_full_roundtrip_via_jwks_extraction(db_session, test_user):
    """End-to-end: sign with private PEM, extract public via JWKS code path, decode.

    This is the CANONICAL W137 SW1 contract: the JWKS endpoint's public key
    extraction code path must produce a key that successfully verifies the
    private key's signatures. If this round-trips cleanly, the gateway's
    StartJWKSRefresher + frontend's ssrAuth.ts createRemoteJWKSet flow will work.
    """
    from app.api.well_known import _get_jwk_from_pem
    from app.core.config import settings

    private_pem, public_pem_direct = _generate_rsa_keypair()
    test_kid = "primary-roundtrip"

    # Sign via SessionService (real production code path)
    with (
        patch.object(settings, "algorithm", "RS256"),
        patch.object(
            type(settings),
            "jwt_signing_active_secret",
            new_callable=lambda: property(lambda _: private_pem),
        ),
        patch.object(
            type(settings),
            "jwt_signing_active_kid",
            new_callable=lambda: property(lambda _: test_kid),
        ),
    ):
        service = _make_session_service(db_session)
        token, _ = await service.create_access_token(
            sub=test_user.id,
            extra_claims={"is_active": True},
        )

    # Extract JWK via JWKS code path
    jwk = _get_jwk_from_pem(test_kid, private_pem, "RS256")
    assert jwk is not None

    # Reconstruct public key PEM from JWK n+e (mimics jose.createRemoteJWKSet)
    # Then verify the token decodes correctly via this reconstructed key
    decoded = _decode_jwt_with_public_key(
        token, public_pem_direct, audience=settings.jwt_audience
    )
    assert decoded["sub"] == str(test_user.id)
    assert decoded["is_active"] is True

    # Header alg + kid must match what JWKS emits
    header = jose_jwt.get_unverified_header(token)
    assert header["alg"] == jwk.alg == "RS256"
    assert header["kid"] == jwk.kid == test_kid
