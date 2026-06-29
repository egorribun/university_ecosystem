from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response

from app.auth import mfa
from app.services.auth.mfa_coordinator import MfaCoordinator


@pytest.fixture
def coordinator():
    uow = AsyncMock()
    repo = AsyncMock()
    return MfaCoordinator(uow, repo)


@pytest.mark.asyncio
async def test_check_and_issue_challenges_no_mfa(coordinator):
    user = MagicMock(id="123", mfa_required=False)
    coordinator.repo.has_active_mfa.return_value = False

    res = await coordinator.check_and_issue_challenges(user, AsyncMock(), None, "en")
    assert res is None


@pytest.mark.asyncio
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._resolve_mfa_capabilities",
    return_value={},
)
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._collect_mfa_challenges",
    return_value=[],
)
async def test_check_and_issue_challenges_no_methods(
    mock_collect, mock_resolve, coordinator
):
    user = MagicMock(id="123", mfa_required=True)
    with pytest.raises(HTTPException) as exc:
        await coordinator.check_and_issue_challenges(user, AsyncMock(), None, "en")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._resolve_mfa_capabilities",
    return_value={"totp": True},
)
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._collect_mfa_challenges",
    return_value=["totp"],
)
async def test_check_and_issue_challenges_with_response(
    mock_collect, mock_resolve, coordinator
):
    user = MagicMock(id="123", mfa_required=True, mfa_default_method=None)
    response = MagicMock(spec=Response)

    res = await coordinator.check_and_issue_challenges(
        user, AsyncMock(), response, "en"
    )
    assert response.status_code == 202
    assert res.default_method == mfa.MFA_METHOD_TOTP
    assert res.methods == ["totp"]
    coordinator.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.auth.mfa.start_totp_verification", new_callable=AsyncMock)
@patch("app.auth.mfa.describe_challenge_attempts", return_value=(1, 5, 4))
async def test_collect_mfa_challenges_totp(mock_describe, mock_start, coordinator):
    user = MagicMock(id="123")
    mock_start.return_value = MagicMock(token="token_totp", expires_at="never")
    capabilities = {mfa.MFA_METHOD_TOTP: True}

    methods = await coordinator._collect_mfa_challenges(user, "en", capabilities, None)

    assert len(methods) == 1
    assert methods[0].method == mfa.MFA_METHOD_TOTP
    assert methods[0].challenge_token == "token_totp"
    assert methods[0].remaining_attempts == 4


@pytest.mark.asyncio
@patch("app.auth.mfa.issue_challenge", new_callable=AsyncMock)
@patch("app.auth.mfa.describe_challenge_attempts", return_value=(1, 5, 4))
@patch(
    "app.services.webauthn.WebAuthnService.get_authentication_options",
    new_callable=AsyncMock,
)
async def test_collect_mfa_challenges_webauthn(
    mock_options, mock_describe, mock_issue, coordinator
):
    user = MagicMock(id="123")
    mock_issue.return_value = MagicMock(token="token_webauthn", expires_at="never")
    mock_options.return_value = "options"
    capabilities = {mfa.MFA_METHOD_WEBAUTHN: True}

    methods = await coordinator._collect_mfa_challenges(user, "en", capabilities, None)

    assert len(methods) == 1
    assert methods[0].method == mfa.MFA_METHOD_WEBAUTHN
    assert methods[0].challenge_token == "token_webauthn"
    assert methods[0].options == "options"
    assert methods[0].remaining_attempts == 4
