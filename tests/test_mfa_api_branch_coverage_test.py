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
