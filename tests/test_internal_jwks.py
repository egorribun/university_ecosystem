from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_internal_jwks_endpoint(root_client: AsyncClient):
    """Test the internal /.well-known/jwks.json endpoint (under /api/v1 prefix)."""
    fake_registry = {
        "kid-active": "secret-active",
        "kid-old": "secret-old",
        "kid-older": "secret-older",
    }

    with patch("app.api.internal.jwks.settings") as mock_settings:
        mock_settings.jwt_signing_key_registry = fake_registry
        mock_settings.jwt_signing_active_kid = "kid-active"
        mock_settings.algorithm = "HS256"

        # Call the internal /api/v1/.well-known/jwks.json route
        response = await root_client.get("/api/v1/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        keys = data["keys"]

        # Verify the structure of keys
        assert len(keys) == 3
        for k in keys:
            assert k["kty"] == "oct"
            assert k["use"] == "sig"
            assert k["alg"] == "HS256"

        # Verify sorting: active_kid must be first
        assert keys[0]["kid"] == "kid-active"

        # All kids should be present
        kids = {k["kid"] for k in keys}
        assert kids == {"kid-active", "kid-old", "kid-older"}
