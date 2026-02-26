"""JWKS endpoint — exposes public signing key metadata for JWT verification.

Microservices (such as ws-hub) and any future service-to-service consumers
can fetch this endpoint to obtain the active signing key identifiers and
algorithm, enabling zero-downtime JWT key rotation without manual secret
distribution.

Current status: HMAC (symmetric) keys — ``kty=oct``.  The ``k`` field
(raw secret) is intentionally omitted; HMAC verification requires the
shared secret itself, which is distributed via the ``JWT_SECRETS`` env var
on each consumer.  The endpoint ONLY exposes metadata (kid, alg, use) so
that consumers can cache key identifiers and detect rotation.

Modernization note (MOD-1): migrate to RS256 / ES256 (asymmetric) so that
the public key can be published here without any secret exposure.  Track via
GitHub issue #MOD-1.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["internal"])


class JwksKey(BaseModel):
    """A single entry in the JSON Web Key Set.

    Follows RFC 7517 (JWK) and RFC 7518 (JWA).
    Only non-secret metadata is exposed for symmetric keys.
    """

    kty: str
    use: str
    alg: str
    kid: str


class JwksResponse(BaseModel):
    keys: list[JwksKey]


@router.get(
    "/.well-known/jwks.json",
    response_model=JwksResponse,
    include_in_schema=False,
    summary="JSON Web Key Set",
    description=(
        "Returns signing key metadata for JWT verification by microservices. "
        "For HMAC keys (kty=oct) the raw secret is NOT included — consumers "
        "must receive shared secrets via environment variables. "
        "Once migrated to RS256/ES256 this endpoint will carry full public keys."
    ),
)
async def get_jwks() -> JwksResponse:
    """Return key metadata for all keys in the active signing registry.

    Designed to be polled by downstream services (ws-hub, gateway, etc.)
    with a short TTL cache (e.g., 5 minutes) so they pick up new keys
    automatically when the Python backend rotates them.
    """
    registry: dict[str, str] = settings.jwt_signing_key_registry
    active_kid: str = settings.jwt_signing_active_kid
    algorithm: str = settings.algorithm

    keys = [
        JwksKey(
            kty="oct",  # Symmetric key type (RFC 7518 §6.4)
            use="sig",  # Intended use: signature verification
            alg=algorithm,  # e.g. HS256
            kid=kid,
        )
        for kid in registry
    ]

    # Place the active (primary) key first so consumers can use the first
    # entry as their default without parsing the full list.
    keys.sort(key=lambda k: (k.kid != active_kid,))

    return JwksResponse(keys=keys)
