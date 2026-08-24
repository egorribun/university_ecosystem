"""MOD-22-01 (Wave 22): Cryptographic rotation and parameter validation tests.

Tests cover:
  - JWT ``kid`` rotation: valid kid accepted, unknown kid rejected, missing kid rejected
  - CSRF HMAC session binding: cross-session tokens are rejected
  - Argon2id parameter validation: memory cost >= 32768 KiB, time cost >= 3
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import jwt

from app.auth.security import (
    ARGON2_MEMORY_COST_KIB,
    ARGON2_TIME_COST,
    argon2_hasher,
    decode_token,
)
from app.core.csrf import (
    _build_signed_token,
    _compute_csrf_hmac,
    _verify_signed_token,
)

# ---------------------------------------------------------------------------
# JWT kid rotation (MOD-22-01)
# ---------------------------------------------------------------------------


class TestJWTKidRotation:
    """Verify that JWT kid-based key selection works correctly."""

    _ACTIVE_KID = "kid-active-v1"
    _ACTIVE_SECRET = (
        "active-secret-key-with-enough-entropy-for-hs256"  # pragma: allowlist secret
    )
    _OLD_KID = "kid-old-v0"
    _OLD_SECRET = (
        "old-secret-key-still-in-registry-for-rotation"  # pragma: allowlist secret
    )
    _UNKNOWN_KID = "kid-unknown-never-registered"
    _AUDIENCE = "university-ecosystem"
    _ALGORITHM = "HS256"

    def _mint_token(
        self,
        *,
        kid: str | None = None,
        secret: str = _ACTIVE_SECRET,
        include_kid: bool = True,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(uuid4()),
            "aud": self._AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=30),
            "jti": str(uuid4()),
            **(extra_claims or {}),
        }
        headers: dict[str, Any] = {}
        if include_kid and kid is not None:
            headers["kid"] = kid
        return jwt.encode(payload, secret, algorithm=self._ALGORITHM, headers=headers)

    def _settings_patch(self) -> dict[str, Any]:
        return {
            "jwt_signing_key_registry": {
                self._ACTIVE_KID: self._ACTIVE_SECRET,
                self._OLD_KID: self._OLD_SECRET,
            },
            "jwt_signing_active_kid": self._ACTIVE_KID,
            "jwt_signing_active_secret": self._ACTIVE_SECRET,
            "algorithm": self._ALGORITHM,
            "jwt_audience": self._AUDIENCE,
        }

    def test_valid_active_kid_accepted(self) -> None:
        """Token signed with the active kid and matching secret is accepted."""
        token = self._mint_token(kid=self._ACTIVE_KID, secret=self._ACTIVE_SECRET)
        with patch("app.auth.security.settings", **self._settings_patch()):
            payload = decode_token(token)
        assert payload is not None
        assert "sub" in payload

    def test_valid_old_kid_accepted(self) -> None:
        """Token signed with an old (but still registered) kid is accepted."""
        token = self._mint_token(kid=self._OLD_KID, secret=self._OLD_SECRET)
        with patch("app.auth.security.settings", **self._settings_patch()):
            payload = decode_token(token)
        assert payload is not None

    def test_unknown_kid_rejected(self) -> None:
        """Token with a kid that is not in the registry is rejected immediately."""
        token = self._mint_token(
            kid=self._UNKNOWN_KID,
            secret="unknown-kid-test-key-at-least-32-bytes",  # pragma: allowlist secret
        )
        with patch("app.auth.security.settings", **self._settings_patch()):
            payload = decode_token(token)
        assert payload is None

    def test_missing_kid_rejected(self) -> None:
        """Token without a kid header is rejected (RZ-10 enforcement)."""
        token = self._mint_token(include_kid=False, secret=self._ACTIVE_SECRET)
        with patch("app.auth.security.settings", **self._settings_patch()):
            payload = decode_token(token)
        assert payload is None

    def test_empty_registry_rejects_all(self) -> None:
        """If the key registry is empty, all tokens are rejected."""
        token = self._mint_token(kid=self._ACTIVE_KID, secret=self._ACTIVE_SECRET)
        patch_settings = self._settings_patch()
        patch_settings["jwt_signing_key_registry"] = {}
        with patch("app.auth.security.settings", **patch_settings):
            assert decode_token(token) is None

    def test_kid_mismatch_secret_rejected(self) -> None:
        """Token signed with wrong secret for a valid kid is rejected."""
        token = self._mint_token(
            kid=self._ACTIVE_KID,
            secret="wrong-test-key-that-is-at-least-32-bytes",  # pragma: allowlist secret
        )
        with patch("app.auth.security.settings", **self._settings_patch()):
            assert decode_token(token) is None


# ---------------------------------------------------------------------------
# CSRF HMAC session binding (MOD-22-01)
# ---------------------------------------------------------------------------


class TestCSRFSessionBinding:
    """Verify that CSRF tokens are bound to the session that created them."""

    _SECRET = b"a-csrf-hmac-secret-with-at-least-32-bytes-of-entropy"

    def test_valid_token_accepted(self) -> None:
        """A token built for a session is accepted for that same session."""
        session_id = "session-abc-123"
        token = _build_signed_token(session_id, self._SECRET)
        assert _verify_signed_token(token, session_id, self._SECRET)

    def test_cross_session_rejected(self) -> None:
        """A token built for session A is rejected when validated against session B."""
        token = _build_signed_token("session-A", self._SECRET)
        assert not _verify_signed_token(token, "session-B", self._SECRET)

    def test_different_secret_rejected(self) -> None:
        """A token is rejected when the server secret has rotated."""
        session_id = "session-same"
        token = _build_signed_token(session_id, self._SECRET)
        new_secret = b"rotated-csrf-hmac-secret-at-least-32-bytes-long!!"
        assert not _verify_signed_token(token, session_id, new_secret)

    def test_malformed_token_rejected(self) -> None:
        """Tokens without the expected nonce.hmac format are rejected."""
        assert not _verify_signed_token("no-separator", "sid", self._SECRET)
        assert not _verify_signed_token("", "sid", self._SECRET)
        assert not _verify_signed_token(".", "sid", self._SECRET)

    def test_hmac_is_session_specific(self) -> None:
        """HMAC output differs for different session IDs with the same nonce."""
        nonce = "fixed-nonce-value"
        mac_a = _compute_csrf_hmac(nonce, "session-A", self._SECRET)
        mac_b = _compute_csrf_hmac(nonce, "session-B", self._SECRET)
        assert mac_a != mac_b


# ---------------------------------------------------------------------------
# Argon2id parameter validation (MOD-22-01)
# ---------------------------------------------------------------------------


class TestArgon2Parameters:
    """Validate that Argon2id parameters meet OWASP ASVS §2.4.4 minimums."""

    def test_memory_cost_minimum(self) -> None:
        """Memory cost must be >= 32768 KiB (32 MiB) per OWASP ASVS §2.4.4."""
        assert ARGON2_MEMORY_COST_KIB >= 32768, (
            f"Argon2 memory_cost={ARGON2_MEMORY_COST_KIB} KiB is below the "
            "OWASP minimum of 32768 KiB (32 MiB)"
        )

    def test_time_cost_minimum(self) -> None:
        """Time cost (iterations) must be >= 3 per OWASP recommendation."""
        assert ARGON2_TIME_COST >= 3, (
            f"Argon2 time_cost={ARGON2_TIME_COST} is below the minimum of 3"
        )

    def test_hasher_uses_argon2id(self) -> None:
        """The hasher must use the Argon2id variant (hybrid side-channel resistance)."""
        from argon2 import Type

        assert argon2_hasher.type == Type.ID

    def test_hasher_parameters_match_constants(self) -> None:
        """The PasswordHasher instance uses the declared constants."""
        assert argon2_hasher.time_cost == ARGON2_TIME_COST
        assert argon2_hasher.memory_cost == ARGON2_MEMORY_COST_KIB

    def test_hash_output_contains_argon2id_prefix(self) -> None:
        """Hashing a password produces an $argon2id$ prefixed string."""
        hashed = argon2_hasher.hash("TestPassword123!")
        assert hashed.startswith("$argon2id$")
