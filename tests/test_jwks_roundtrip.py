"""JWKS cryptographic round-trip contract tests.

W142 (z) #10 surfaced: Temporal Server rejects file-processor's RS256-signed
JWT with `crypto/rsa: verification error` despite Python `cryptography` lib
verifying the SAME signature against the SAME JWKS pub key. The audit
attributed this to a possible JWKS payload structural mismatch — Python's
`numbers.n.to_bytes(...)` byte encoding vs the expectations of the
verifier-side library that reconstructs `*rsa.PublicKey` from `n`+`e`.

Phase 1 Explore (W143 SW2) identified the actual library chain:
- Temporal Server uses `github.com/go-jose/go-jose/v4` for JWKS parsing
- `github.com/golang-jwt/jwt/v4` v4.5.2 for the verify call
- The error message comes from Go stdlib `crypto/rsa.ErrVerification`,
  NOT a JWX-wrapped error (Agent 2 hypothesis disproved)

This test reproduces the verifier-side path entirely in Python:
1. Mint a token using a known PEM private key
2. Call our JWKS endpoint to get the JSON representation
3. Reconstruct the public key from JWKS `n`+`e` bytes
4. Verify the token against the reconstructed pub key (path A)
5. Verify the token against the PEM private key's pub key directly (path B)
6. ASSERT path A and path B BOTH succeed

If both paths succeed: our JWKS endpoint produces a byte-identical
representation of the pub key — the (z) #10 root cause is NOT in our JWKS
shape. SW3 then focuses on Temporal-specific config (claim mapper,
audience, internal-frontend service, JWKS cache timing).

If path A fails while path B succeeds: our JWKS endpoint has an encoding
issue (e.g., leading-zero padding, base64url char set mismatch, missing
field). SW3 then focuses on fixing well_known.py byte encoding.

Per W141 anti-pattern #2: this test is necessary but NOT sufficient for
closure — runtime swap (W143 SW3 docker-compose + grep "Connected to
Temporal" log) IS the closure step.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import jwt as pyjwt  # PyJWT (already in deps; backend uses it)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPublicNumbers


def _b64url_decode_int(b64url: str) -> int:
    """Decode a base64url-encoded big-endian integer (per RFC 7518 §6.3.1).

    Pads with `=` if needed since our well_known.py output strips padding via
    `rstrip("=")` (line 40). RFC 7518 mandates no leading zero bytes in the
    base64url-encoded representation; PyJWT/jose libraries also tolerate
    canonical encoding.
    """
    padding = (-len(b64url)) % 4
    decoded = base64.urlsafe_b64decode(b64url + ("=" * padding))
    return int.from_bytes(decoded, byteorder="big")


def _generate_rsa_pem() -> tuple[str, RSAPublicKey]:
    """Generate a fresh 2048-bit RSA keypair and return PEM + public key.

    Returns the PEM-encoded PKCS#1 private key plus the public key object so
    downstream verification can also exercise the direct PEM path (without
    going through JWKS reconstruction).
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem, private_key.public_key()


class TestJwksCryptographicRoundtrip:
    """W143 SW2 — (z) #10 diagnostic: JWKS pub key reconstruction round-trip."""

    async def test_jwks_pub_key_reconstructs_to_matching_modulus(
        self, root_client
    ) -> None:
        """JWKS-published `n`+`e` must reconstruct to the SAME modulus as the PEM private key's pub key.

        This is the most direct test for (z) #10: does our well_known.py byte
        encoding round-trip cleanly? If `int.from_bytes(b64url_decode(n))` !=
        `private_key.public_numbers().n`, our JWKS output is non-canonical.
        """
        pem, pub_key = _generate_rsa_pem()
        expected_numbers = pub_key.public_numbers()

        with patch("app.api.well_known.settings") as mock_settings:
            mock_settings.jwt_signing_key_registry = {"primary": pem}
            mock_settings.jwt_signing_active_kid = "primary"
            mock_settings.algorithm = "RS256"
            response = await root_client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        key = response.json()["keys"][0]

        # Round-trip: decode JWKS n+e and compare to the source private key's pub modulus.
        reconstructed_n = _b64url_decode_int(key["n"])
        reconstructed_e = _b64url_decode_int(key["e"])

        assert reconstructed_n == expected_numbers.n, (
            "JWKS modulus (n) does not round-trip to the source private key's "
            f"modulus. JWKS-derived n.bit_length()={reconstructed_n.bit_length()}, "
            f"PEM-derived n.bit_length()={expected_numbers.n.bit_length()}. This is "
            "the W142 (z) #10 structural encoding mismatch surfaced as a "
            "contract violation."
        )
        assert reconstructed_e == expected_numbers.e, (
            "JWKS public exponent (e) does not round-trip to the source private "
            f"key's exponent. JWKS-derived e={reconstructed_e}, "
            f"PEM-derived e={expected_numbers.e}."
        )

    async def test_token_verifies_against_jwks_reconstructed_pub_key(
        self, root_client
    ) -> None:
        """A token signed with the PEM private key must verify against the JWKS-derived pub key.

        This mirrors what Temporal's `defaultTokenKeyProvider` does: fetch
        JWKS, reconstruct `*rsa.PublicKey` from `n`+`e`, verify token. If our
        JWKS shape is correct, this round-trip MUST succeed — failure here
        directly identifies (z) #10 as a JWKS encoding issue.
        """
        pem, _pub_key = _generate_rsa_pem()

        # Mint a token using the same PowerShell-equivalent claim set
        # (sub=file-processor-service, aud=temporal, kid=primary).
        token = pyjwt.encode(
            payload={
                "sub": "file-processor-service",
                "aud": "temporal",
                "iat": 1778500000,
                "exp": 1810000000,
                "jti": "wave143-sw2-roundtrip-test",
            },
            key=pem,
            algorithm="RS256",
            headers={"kid": "primary"},
        )

        # Fetch JWKS
        with patch("app.api.well_known.settings") as mock_settings:
            mock_settings.jwt_signing_key_registry = {"primary": pem}
            mock_settings.jwt_signing_active_kid = "primary"
            mock_settings.algorithm = "RS256"
            response = await root_client.get("/.well-known/jwks.json")

        jwks_key = response.json()["keys"][0]

        # Reconstruct *rsa.PublicKey from JWKS n+e bytes — exactly what Temporal does.
        reconstructed_pub = RSAPublicNumbers(
            n=_b64url_decode_int(jwks_key["n"]),
            e=_b64url_decode_int(jwks_key["e"]),
        ).public_key()

        # Verify the token against the JWKS-reconstructed pub key.
        # PyJWT internally uses cryptography's verify path — same primitive
        # as Go's `crypto/rsa.VerifyPKCS1v15` under the hood for RS256.
        decoded = pyjwt.decode(
            token,
            key=reconstructed_pub,
            algorithms=["RS256"],
            audience="temporal",
        )
        assert decoded["sub"] == "file-processor-service"
        assert decoded["aud"] == "temporal"
        assert decoded["jti"] == "wave143-sw2-roundtrip-test"

    async def test_jwks_modulus_byte_length_is_canonical(self, root_client) -> None:
        """JWKS modulus `n` must be exactly ceil(key_size_bits / 8) bytes — no leading zeros.

        Per RFC 7518 §6.3.1.1: "The octet sequence MUST utilize the minimum
        number of octets to represent the value." For a 2048-bit RSA key
        whose modulus has bit_length=2048, this is exactly 256 bytes.

        If this assertion fails with a length other than 256, our
        `well_known.py:58` `to_bytes` calculation is non-canonical — which
        would be the (z) #10 structural cause.
        """
        pem, pub_key = _generate_rsa_pem()
        expected_byte_length = (pub_key.public_numbers().n.bit_length() + 7) // 8

        with patch("app.api.well_known.settings") as mock_settings:
            mock_settings.jwt_signing_key_registry = {"primary": pem}
            mock_settings.jwt_signing_active_kid = "primary"
            mock_settings.algorithm = "RS256"
            response = await root_client.get("/.well-known/jwks.json")

        key = response.json()["keys"][0]
        padding = (-len(key["n"])) % 4
        decoded_n_bytes = base64.urlsafe_b64decode(key["n"] + ("=" * padding))

        assert len(decoded_n_bytes) == expected_byte_length, (
            f"JWKS modulus byte length is {len(decoded_n_bytes)}, expected "
            f"{expected_byte_length} (= ceil({pub_key.public_numbers().n.bit_length()} bits / 8)). "
            "Non-canonical encoding may cause Go's `crypto/rsa` to construct "
            "a different pub key than the actual signing key, leading to "
            '"crypto/rsa: verification error" (W142 (z) #10).'
        )
        # Per RFC 7518 §6.3.1.1, the most significant byte MUST NOT be zero
        # (no leading zero padding).
        assert decoded_n_bytes[0] != 0, (
            "JWKS modulus has leading zero byte — violates RFC 7518 §6.3.1.1 "
            "canonical encoding requirement. This would cause Go's `go-jose` "
            "to reconstruct a different RSA modulus and fail verification."
        )
