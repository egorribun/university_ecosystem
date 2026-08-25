import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import User


@pytest.mark.asyncio
async def test_verify_mfa_challenge_invalid_method():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        headers = {"Authorization": "Bearer test-bypass"}
        response = await ac.post(
            "/api/v1/auth/mfa/verify",
            json={"challenge_token": "a" * 32, "method": "invalid", "code": "123456"},
            headers=headers,
        )
        # Pydantic validation should catch 'invalid' literal → 422
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_mfa_challenge_binding_failure_is_generic():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        headers = {"Authorization": "Bearer test-bypass"}
        with patch(
            "app.api.auth.login.mfa.consume_challenge",
            AsyncMock(side_effect=HTTPException(400, "binding mismatch")),
        ):
            response = await ac.post(
                "/api/v1/auth/mfa/verify",
                json={"challenge_token": "a" * 32, "method": "totp", "code": "123456"},
                headers=headers,
            )
            assert response.status_code == 400
            assert response.json()["detail"] == "MFA verification failed"


@pytest.mark.asyncio
async def test_register_value_error():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        headers = {"Authorization": "Bearer test-bypass"}
        with patch(
            "app.services.user.compliance_service.UserComplianceService.register_user",
            AsyncMock(side_effect=ValueError("Invalid data")),
        ):
            response = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": "valid@example.com",
                    "password": "password12345",  # Ensure min length
                    "full_name": "Name",
                },
                headers=headers,
            )
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_session_signing_key_missing():
    # We need a user to be "logged in" but the session missing from state
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        from app.api.deps import get_current_user

        user = MagicMock(spec=User)
        user.id = secrets.token_hex(16)
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            response = await ac.get("/api/v1/auth/session/signing-key")
            assert response.status_code == 400
        finally:
            del app.dependency_overrides[get_current_user]
