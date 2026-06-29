import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.api.auth.login import login_passkey_verify, register
from app.auth.schemas import LoginPasskeyVerifyIn

@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
async def test_login_passkey_verify_invalid_challenge(mock_get_challenge):
    mock_get_challenge.side_effect = HTTPException(status_code=404)
    payload = MagicMock(spec=LoginPasskeyVerifyIn, challenge_token="token", webauthn_response={})
    request = MagicMock()
    import typing
    async def mock_get(dep, *a, **kw):
        if dep is typing.Any: return AsyncMock()
        if 'LoginService' in str(dep): return AsyncMock()
    request.state.dishka_container.get.side_effect = mock_get
    
    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload,
            response=MagicMock(),
            request=request,
            bg_tasks=MagicMock()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid challenge"

@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
@patch("app.services.webauthn.WebAuthnService.verify_authentication", new_callable=AsyncMock)
async def test_login_passkey_verify_verification_fails(mock_verify, mock_get_challenge):
    challenge = MagicMock(user_id="123", payload={"options": {"challenge": "c"}})
    mock_get_challenge.return_value = challenge
    db = AsyncMock()
    user = MagicMock(is_active=True)
    db.get.return_value = user
    
    mock_verify.side_effect = Exception("WebAuthn error")
    
    payload = MagicMock(spec=LoginPasskeyVerifyIn, challenge_token="token", webauthn_response={})
    request = MagicMock()
    import typing
    async def mock_get(dep, *a, **kw):
        if dep is typing.Any: return db
        if 'LoginService' in str(dep): return AsyncMock()
    request.state.dishka_container.get.side_effect = mock_get
    
    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload,
            response=MagicMock(),
            request=request,
            bg_tasks=MagicMock()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Passkey verification failed"

@pytest.mark.asyncio
async def test_register_value_error():
    user = MagicMock()
    compliance_service = AsyncMock()
    compliance_service.register_user.side_effect = ValueError("Duplicate email")
    db = AsyncMock()
    request = MagicMock()
    import typing
    async def mock_get(dep, *a, **kw):
        if dep is typing.Any: return db
        if 'LoginService' in str(dep): return AsyncMock()
        if 'UserComplianceService' in str(dep): return compliance_service
    request.state.dishka_container.get.side_effect = mock_get
    
    with pytest.raises(HTTPException) as exc:
        await register(
            user=user,
            request=request
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Duplicate email"
    db.rollback.assert_awaited_once()
