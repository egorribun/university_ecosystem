import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import User


@pytest.mark.asyncio
async def test_login_passkey_start_user_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        # Add Bearer header to bypass CSRF middleware
        headers = {"Authorization": "Bearer test-bypass"}
        with patch(
            "app.services.user.profile_service.UserProfileService.get_user_by_email",
            AsyncMock(return_value=None),
        ):
            with patch("app.auth.mfa.challenge.issue_dummy_challenge", AsyncMock()):
                with patch("app.api.auth.login.ensure_minimum_time", AsyncMock()):
                    response = await ac.post(
                        "/api/v1/auth/login/passkey/start",
                        json={"email": "missing@example.com"},
                        headers=headers,
                    )
                    assert response.status_code == 200, f"Error: {response.text}"
                    assert "publicKey" in response.json()


@pytest.mark.asyncio
async def test_login_passkey_verify_invalid_challenge():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        headers = {"Authorization": "Bearer test-bypass"}
        with patch(
            "app.auth.mfa.get_challenge",
            AsyncMock(side_effect=HTTPException(400, "Invalid challenge")),
        ):
            response = await ac.post(
                "/api/v1/auth/login/passkey/verify",
                json={"challenge_token": "a" * 32, "webauthn_response": {}},
                headers=headers,
            )
            assert response.status_code == 400, f"Error: {response.text}"


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
async def test_verify_mfa_challenge_fingerprint_mismatch():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        headers = {"Authorization": "Bearer test-bypass"}
        with patch(
            "app.api.auth.login.verify_mfa_fingerprint", AsyncMock(return_value=False)
        ):
            response = await ac.post(
                "/api/v1/auth/mfa/verify",
                json={"challenge_token": "a" * 32, "method": "totp", "code": "123456"},
                headers=headers,
            )
            assert response.status_code == 403


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
