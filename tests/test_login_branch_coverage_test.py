from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.auth.login import login_passkey_verify, register
from app.auth.schemas import LoginPasskeyVerifyIn


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
async def test_login_passkey_verify_invalid_challenge(mock_get_challenge):
    mock_get_challenge.side_effect = HTTPException(status_code=404)
    payload = MagicMock(
        spec=LoginPasskeyVerifyIn, challenge_token="token", webauthn_response={}
    )
    request = MagicMock()
    import typing

    async def mock_get(dep, *a, **kw):
        if dep is typing.Any:
            return AsyncMock()
        if "LoginService" in str(dep):
            return AsyncMock()

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload, response=MagicMock(), request=request, bg_tasks=MagicMock()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid challenge"


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
@patch(
    "app.services.webauthn.WebAuthnService.verify_authentication",
    new_callable=AsyncMock,
)
async def test_login_passkey_verify_verification_fails(mock_verify, mock_get_challenge):
    challenge = MagicMock(user_id="123", payload={"options": {"challenge": "c"}})
    mock_get_challenge.return_value = challenge
    db = AsyncMock()
    user = MagicMock(is_active=True)
    db.get.return_value = user

    mock_verify.side_effect = Exception("WebAuthn error")

    payload = MagicMock(
        spec=LoginPasskeyVerifyIn, challenge_token="token", webauthn_response={}
    )
    request = MagicMock()
    import typing

    async def mock_get(dep, *a, **kw):
        if dep is typing.Any:
            return db
        if "LoginService" in str(dep):
            return AsyncMock()

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload, response=MagicMock(), request=request, bg_tasks=MagicMock()
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
        if dep is typing.Any:
            return db
        if "LoginService" in str(dep):
            return AsyncMock()
        if "UserComplianceService" in str(dep):
            return compliance_service

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await register(user=user, request=request)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Duplicate email"
    db.rollback.assert_awaited_once()


import uuid

from app.api.auth.login import (
    login_json,
    login_passkey_start,
    verify_mfa_challenge,
)


@pytest.mark.asyncio
@patch("app.api.auth.login.mfa.issue_challenge", new_callable=AsyncMock)
@patch(
    "app.services.webauthn.WebAuthnService.get_authentication_options",
    new_callable=AsyncMock,
)
async def test_login_passkey_start_user_found_and_active(
    mock_get_options, mock_issue_challenge
):
    mock_get_options.return_value = {"publicKey": "options"}
    challenge = MagicMock(id="challenge_id", token="token")
    mock_issue_challenge.return_value = challenge

    user = MagicMock(id="user_id", is_active=True)
    profile_service = AsyncMock()
    profile_service.get_user_by_email.return_value = user

    db = AsyncMock()
    audit = MagicMock()

    payload = MagicMock()
    payload.email = "test@example.com"
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "UserProfileService" in str(dep):
            return profile_service
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)

    with patch("app.api.auth.login.ensure_minimum_time", AsyncMock()):
        res = await login_passkey_start(
            payload=payload,
            request=request,
        )
    assert res.publicKey == {"publicKey": "options"}
    assert res.challenge_token == "token"
    db.commit.assert_awaited_once()
    audit.log.assert_called_once()


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
async def test_login_passkey_verify_user_inactive_or_none(mock_get_challenge):
    challenge = MagicMock(user_id="123", payload={"options": {"challenge": "c"}})
    mock_get_challenge.return_value = challenge

    db = AsyncMock()
    db.get.return_value = None  # User not found

    payload = MagicMock(challenge_token="token", webauthn_response={})
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return AsyncMock()
        return db

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload, response=MagicMock(), request=request, bg_tasks=MagicMock()
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "User not found or inactive"


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
async def test_login_passkey_verify_payload_none(mock_get_challenge):
    challenge = MagicMock(user_id="123", payload=None)
    mock_get_challenge.return_value = challenge

    db = AsyncMock()
    user = MagicMock(is_active=True)
    db.get.return_value = user

    payload = MagicMock(challenge_token="token", webauthn_response={})
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return AsyncMock()
        return db

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await login_passkey_verify(
            payload=payload, response=MagicMock(), request=request, bg_tasks=MagicMock()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid challenge payload"


@pytest.mark.asyncio
@patch("app.api.auth.login.store_mfa_challenge_fingerprints", new_callable=AsyncMock)
async def test_login_json_pending_mfa(mock_store_fingerprints):
    from app.auth.schemas import PendingMfaResponse

    u_id = uuid.uuid4()
    s_id = uuid.uuid4()

    pending_mfa = PendingMfaResponse(
        user_id=u_id, session_id=s_id, default_method="totp", methods=[]
    )

    login_service = AsyncMock()
    login_service.perform_login.return_value = pending_mfa

    payload = MagicMock(email="test@example.com", password="pass", trust_device=True)
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return login_service
        return AsyncMock()

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)

    res = await login_json(
        payload=payload,
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
    )
    assert res == pending_mfa
    mock_store_fingerprints.assert_awaited_once_with(request, pending_mfa.methods)


@pytest.mark.asyncio
@patch("app.api.auth.login.verify_mfa_fingerprint", new_callable=AsyncMock)
@patch("app.api.auth.login.mfa.consume_challenge", new_callable=AsyncMock)
async def test_verify_mfa_challenge_branches(
    mock_consume_challenge, mock_verify_fingerprint
):
    from app.auth.constants import (
        MFA_METHOD_RECOVERY_CODE,
        MFA_METHOD_TOTP,
        MFA_METHOD_WEBAUTHN,
    )
    from app.auth.schemas import MfaVerifyIn

    db = AsyncMock()
    user = MagicMock(id="user_id")
    db.get.return_value = user
    login_service = AsyncMock()

    request = MagicMock()
    mock_verify_fingerprint.return_value = True

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return login_service
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)

    # 1. TOTP path
    challenge = MagicMock(user_id="user_id", challenge_type="totp_verify")
    mock_consume_challenge.return_value = (challenge, None)

    payload = MfaVerifyIn(
        challenge_token="a" * 32, method=MFA_METHOD_TOTP, code="123456"
    )
    await verify_mfa_challenge(
        payload=payload,
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
    )
    mock_consume_challenge.assert_awaited_with(
        db,
        challenge_token="a" * 32,
        challenge_type="totp-verify",
        provided_code="123456",
        provided_webauthn_response=None,
        provided_method=MFA_METHOD_TOTP,
    )

    # 2. WEBAUTHN path
    challenge = MagicMock(user_id="user_id", challenge_type="webauthn-authentication")
    mock_consume_challenge.return_value = (challenge, None)

    payload = MfaVerifyIn(
        challenge_token="a" * 32, method=MFA_METHOD_WEBAUTHN, webauthn_response={}
    )
    await verify_mfa_challenge(
        payload=payload,
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
    )
    mock_consume_challenge.assert_awaited_with(
        db,
        challenge_token="a" * 32,
        challenge_type="webauthn-authentication",
        provided_code=None,
        provided_webauthn_response={},
        provided_method=MFA_METHOD_WEBAUTHN,
    )

    # 3. RECOVERY_CODE path
    challenge = MagicMock(user_id="user_id", challenge_type="totp-verify")
    mock_consume_challenge.return_value = (challenge, None)

    payload = MfaVerifyIn(
        challenge_token="a" * 32, method=MFA_METHOD_RECOVERY_CODE, code="123456"
    )
    await verify_mfa_challenge(
        payload=payload,
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
    )
    mock_consume_challenge.assert_awaited_with(
        db,
        challenge_token="a" * 32,
        challenge_type=["totp-verify", "webauthn-authentication"],
        provided_code="123456",
        provided_webauthn_response=None,
        provided_method=MFA_METHOD_RECOVERY_CODE,
    )

    # 4. User not found path
    db.get.return_value = None
    payload = MfaVerifyIn(
        challenge_token="a" * 32, method=MFA_METHOD_TOTP, code="123456"
    )
    with pytest.raises(HTTPException) as exc:
        await verify_mfa_challenge(
            payload=payload,
            response=MagicMock(),
            request=request,
            bg_tasks=MagicMock(),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

    # 5. Invalid MFA method path
    payload = MagicMock()
    payload.method = "invalid-method"
    payload.challenge_token = "a" * 32
    with pytest.raises(HTTPException) as exc:
        await verify_mfa_challenge(
            payload=payload,
            response=MagicMock(),
            request=request,
            bg_tasks=MagicMock(),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid MFA method"


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
@patch(
    "app.services.webauthn.WebAuthnService.verify_authentication",
    new_callable=AsyncMock,
)
async def test_login_passkey_verify_success(mock_verify, mock_get_challenge):
    from app.schemas.schemas import TokenWithProfile

    challenge = MagicMock(user_id="123", payload={"options": {"challenge": "c"}})
    mock_get_challenge.return_value = challenge

    db = AsyncMock()
    user = MagicMock(is_active=True)
    db.get.return_value = user

    login_service = AsyncMock()
    login_service.finalize_login.return_value = MagicMock(spec=TokenWithProfile)

    payload = MagicMock(challenge_token="token", webauthn_response={})
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return login_service
        return db

    request.state.dishka_container.get.side_effect = mock_get

    res = await login_passkey_verify(
        payload=payload, response=MagicMock(), request=request, bg_tasks=MagicMock()
    )
    assert res is not None
    mock_verify.assert_awaited_once()
