"""Unit tests for the JWKS endpoint (MOD-1 / audit 2026-02-24)."""

from __future__ import annotations

from unittest.mock import patch


class TestGetJwks:
    async def test_returns_all_registered_keys(self, async_client) -> None:  # type: ignore[no-untyped-def]
        """Every key in the signing registry must appear in the response."""
        fake_registry = {"kid-a": "secret-a", "kid-b": "secret-b"}
        with (
            patch("app.api.internal.jwks.settings") as mock_settings,
        ):
            mock_settings.jwt_signing_key_registry = fake_registry
            mock_settings.jwt_signing_active_kid = "kid-a"
            mock_settings.algorithm = "HS256"
            response = await async_client.get("/api/v1/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()
        kids = {k["kid"] for k in data["keys"]}
        assert kids == {"kid-a", "kid-b"}

    async def test_active_key_is_first(self, async_client) -> None:  # type: ignore[no-untyped-def]
        """Active key (primary) must be first in the keys array."""
        fake_registry = {"kid-primary": "s1", "kid-old": "s2"}
        with patch("app.api.internal.jwks.settings") as mock_settings:
            mock_settings.jwt_signing_key_registry = fake_registry
            mock_settings.jwt_signing_active_kid = "kid-primary"
            mock_settings.algorithm = "HS256"
            response = await async_client.get("/api/v1/.well-known/jwks.json")

        keys = response.json()["keys"]
        assert keys[0]["kid"] == "kid-primary"

    async def test_key_metadata_fields(self, async_client) -> None:  # type: ignore[no-untyped-def]
        """Each key entry must have the correct RFC 7517 fields (no raw secret)."""
        with patch("app.api.internal.jwks.settings") as mock_settings:
            mock_settings.jwt_signing_key_registry = {"k1": "secret"}
            mock_settings.jwt_signing_active_kid = "k1"
            mock_settings.algorithm = "HS256"
            response = await async_client.get("/api/v1/.well-known/jwks.json")

        key = response.json()["keys"][0]
        assert key["kty"] == "oct"
        assert key["use"] == "sig"
        assert key["alg"] == "HS256"
        assert key["kid"] == "k1"
        # Raw secret must NEVER appear in the response.
        assert "k" not in key
        assert "secret" not in str(response.json())
