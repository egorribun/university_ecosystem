from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.auth.mfa import confirm_totp_enrollment, confirm_webauthn_registration
from app.auth.schemas import TotpEnrollmentConfirmIn
from app.schemas.schemas import WebAuthnRegistrationVerifyIn


@pytest.mark.asyncio
@patch("app.auth.mfa.complete_totp_enrollment", new_callable=AsyncMock)
async def test_confirm_totp_enrollment_failure(mock_complete):
    mock_complete.side_effect = HTTPException(status_code=400)

    payload = MagicMock(
        spec=TotpEnrollmentConfirmIn, enrollment_id="123", code="123456"
    )
    db = AsyncMock()
    enrollment = MagicMock(user_id="user_123")
    db.get.return_value = enrollment
    audit = MagicMock()
    user = MagicMock(id="user_123")

    request = MagicMock()
    import typing

    async def mock_get(dep, *a, **kw):
        if dep is typing.Any:
            return db
        if "AuditService" in str(dep):
            return audit

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(payload=payload, request=request, user=user)
    assert exc.value.status_code == 400
    audit.log.assert_called_with(
        "auth.mfa.totp.enroll_failure",
        request,
        user_id="user_123",
        reason="invalid_code",
        extra={"enrollment_id": "123"},
    )


@pytest.mark.asyncio
@patch("app.auth.mfa.get_challenge", new_callable=AsyncMock)
@patch(
    "app.services.webauthn.WebAuthnService.verify_registration", new_callable=AsyncMock
)
async def test_confirm_webauthn_registration_failure(mock_verify, mock_get_challenge):
    mock_verify.side_effect = Exception("Registration Error")

    challenge = MagicMock(payload={"options": {"challenge": "abc"}})
    mock_get_challenge.return_value = challenge

    payload = MagicMock(
        spec=WebAuthnRegistrationVerifyIn, challenge="token", response={}, label="mykey"
    )
    db = AsyncMock()
    audit = AsyncMock()
    user = MagicMock(id="user_123")

    request = MagicMock()
    import typing

    async def mock_get(dep, *a, **kw):
        if dep is typing.Any:
            return db
        if "AuditService" in str(dep):
            return audit

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await confirm_webauthn_registration(payload=payload, request=request, user=user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Passkey verification failed"


from app.api.auth.mfa import delete_webauthn_credential, request_step_up


@pytest.mark.asyncio
async def test_confirm_totp_enrollment_not_found():
    from app.auth.schemas import TotpEnrollmentConfirmIn

    # 1. Enrollment is None
    payload = MagicMock(
        spec=TotpEnrollmentConfirmIn, enrollment_id="123", code="123456"
    )
    db = AsyncMock()
    db.get.return_value = None

    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        return db

    request.state.dishka_container.get.side_effect = mock_get

    user = MagicMock(id="user_123")

    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(payload=payload, request=request, user=user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Enrollment not found"

    # 2. Enrollment belongs to different user
    enrollment = MagicMock(user_id="user_other")
    db.get.return_value = enrollment
    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(payload=payload, request=request, user=user)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Enrollment not found"


@pytest.mark.asyncio
async def test_delete_webauthn_credential_not_found():
    db = AsyncMock()
    db.get.return_value = None

    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        return db

    request.state.dishka_container.get.side_effect = mock_get

    user = MagicMock(id="user_123")

    with pytest.raises(HTTPException) as exc:
        await delete_webauthn_credential(
            credential_id="cred_123", request=request, user=user
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Credential not found"

    # Credential belongs to different user
    cred = MagicMock(user_id="user_other")
    db.get.return_value = cred
    with pytest.raises(HTTPException) as exc:
        await delete_webauthn_credential(
            credential_id="cred_123", request=request, user=user
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Credential not found"


@pytest.mark.asyncio
@patch("app.api.auth.mfa.mfa.user_has_confirmed_interactive_factor", return_value=False)
@patch(
    "app.models.user_loaders.ensure_mfa_relationships_loaded", new_callable=AsyncMock
)
async def test_request_step_up_missing_interactive_factor(
    mock_ensure_loaded, mock_has_factor
):
    db = AsyncMock()
    audit = MagicMock()
    login_service = AsyncMock()

    request = MagicMock()
    request.state.active_session = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return login_service
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)

    user = MagicMock(id="user_123")

    with pytest.raises(HTTPException) as exc:
        await request_step_up(request=request, user=user)
    assert exc.value.status_code == 400


from app.api.auth.mfa import generate_recovery_codes_endpoint


@pytest.mark.asyncio
@patch("app.api.auth.mfa.mfa.generate_recovery_codes", new_callable=AsyncMock)
async def test_generate_recovery_codes_endpoint(mock_generate):
    mock_generate.return_value = ["code1", "code2"]

    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)
    user = MagicMock(id="user_123")

    res = await generate_recovery_codes_endpoint(request=request, user=user)
    assert res.codes == ["code1", "code2"]
    db.commit.assert_awaited_once()
    audit.log.assert_called_once()
