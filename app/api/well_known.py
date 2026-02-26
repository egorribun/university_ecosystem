from __future__ import annotations

import base64
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, settings

router = APIRouter()
_logger = logging.getLogger(__name__)


class JWK(BaseModel):
    kty: str
    use: str = "sig"
    kid: str
    alg: str
    n: str
    e: str


class JWKS(BaseModel):
    keys: list[JWK]


def _to_base64url(val: bytes) -> str:
    return base64.urlsafe_b64encode(val).decode("ascii").rstrip("=")


def _get_jwk_from_pem(kid: str, pem_content: str, alg: str) -> JWK | None:
    try:
        # Check if it looks like a PEM block
        if not pem_content.strip().startswith("-----BEGIN"):
            return None

        key = serialization.load_pem_private_key(pem_content.encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            return None

        public_key = key.public_key()
        numbers = public_key.public_numbers()

        # Base64URL encode modulus and exponent
        # Modulus n and exponent e must be encoded as big-endian bytes
        n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, byteorder="big")
        e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, byteorder="big")

        return JWK(
            kty="RSA",
            use="sig",
            kid=kid,
            alg=alg,
            n=_to_base64url(n_bytes),
            e=_to_base64url(e_bytes),
        )
    except Exception as exc:
        _logger.warning("Failed to generate JWK for kid %s: %s", kid, exc)
        return None


@router.get("/jwks.json", response_model=JWKS)
async def get_jwks(s: Settings = Depends(lambda: settings)) -> JWKS:
    """Expose public keys in JWKS format for RS256 token verification.

    (MOD-1: audit 2026-02-24)
    """
    keys: list[JWK] = []

    # We only expose keys if we are using an asymmetric algorithm
    if s.algorithm != "RS256":
        return JWKS(keys=[])

    registry = s.jwt_signing_key_registry
    for kid, secret in registry.items():
        jwk = _get_jwk_from_pem(kid, secret, s.algorithm)
        if jwk:
            keys.append(jwk)

    return JWKS(keys=keys)
