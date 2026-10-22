"""Database-backed email MFA and trusted-device flow, up to session finalization.

Session issuance is mocked at finalize_login; these are not full login E2E tests.
"""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, Request, Response
from sqlalchemy import select

from app.api.auth import login as login_api
from app.auth.mfa.email_otp import EmailOtpService
from app.auth.schemas import MfaVerifyIn
from app.core.config import settings
from app.models import ChallengeState, MfaChallenge, TrustedDevice
from app.repositories.auth_repository import AuthRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.auth.login_service import LoginService
from app.services.auth.mfa_coordinator import MfaCoordinator


def _request(cookies: dict[str, str] | None = None) -> Request:
    headers = [(b"user-agent", b"synthetic-email-mfa-agent")]
    if cookies:
        headers.append(
            (
                b"cookie",
                "; ".join(f"{key}={value}" for key, value in cookies.items()).encode(),
            )
        )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/mfa/verify",
            "headers": headers,
            "query_string": b"",
            "client": ("203.0.113.8", 4321),
            "scheme": "https",
            "server": ("testserver", 443),
        }
    )


def _cookies(response: Response) -> SimpleCookie:
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        cookies.load(header)
    return cookies


@pytest.mark.asyncio
@pytest.mark.parametrize("trust_device", [False, True])
async def test_email_mfa_persisted_trust_choice_controls_next_login(
    db_session, user_factory, monkeypatch, trust_device
) -> None:
    now = datetime.now(UTC)
    user = await user_factory(
        email="email-mfa-login@example.com",
        email_verified_at=now - timedelta(days=1),
        email_mfa_enabled_at=now - timedelta(hours=1),
        mfa_required=True,
        mfa_default_method="email_otp",
        mfa_epoch=4,
    )
    otp_service = EmailOtpService(
        hmac_keys={"test-hmac": b"h" * 32},
        active_hmac_key_id="test-hmac",
        delivery_keks={"test-kek": b"k" * 32},
        active_kek_id="test-kek",
        rate_limiter=AsyncMock(),
    )
    monkeypatch.setattr("app.auth.mfa.email_otp._generate_otp", lambda: "482913")
    coordinator = MfaCoordinator(
        uow_from_session(db_session), AuthRepository(db_session), otp_service
    )
    initial_response = Response()
    pending = await coordinator.check_and_issue_challenges(
        user, _request(), initial_response, "en", trust_device=trust_device
    )
    await db_session.commit()

    assert pending is not None
    assert pending.default_method == "email_otp"
    assert initial_response.status_code == 202
    assert len(pending.methods) == 1
    method = pending.methods[0]
    assert method.method == "email_otp"
    preauth_cookie = _cookies(initial_response)[MfaCoordinator.PREAUTH_COOKIE_NAME]
    assert preauth_cookie["httponly"]
    challenge = (
        await db_session.execute(
            select(MfaChallenge).where(MfaChallenge.user_id == user.id)
        )
    ).scalar_one()
    assert challenge.state == ChallengeState.PENDING
    assert challenge.trust_device_requested is trust_device
    assert challenge.session_identifier == preauth_cookie.value

    login_service = LoginService(MagicMock(), coordinator, MagicMock(), db_session)
    finalized = object()
    finalize_login = AsyncMock(return_value=finalized)
    monkeypatch.setattr(login_service, "finalize_login", finalize_login)
    verification_response = Response()
    result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
        MfaVerifyIn(
            method="email_otp", challenge_token=method.challenge_token, code="482913"
        ),
        verification_response,
        _request({MfaCoordinator.PREAUTH_COOKIE_NAME: preauth_cookie.value}),
        BackgroundTasks(),
        login_service,
        db_session,
    )
    await db_session.commit()
    await db_session.refresh(challenge)

    assert result is finalized
    assert challenge.state == ChallengeState.CONSUMED
    finalize_login.assert_awaited_once()
    assert finalize_login.await_args.kwargs["user"].id == user.id
    assert finalize_login.await_args.kwargs["mfa_completed"] is True
    assert finalize_login.await_args.kwargs["method"] == "email_otp"
    verified_cookies = _cookies(verification_response)
    assert verified_cookies[MfaCoordinator.PREAUTH_COOKIE_NAME]["max-age"] == "0"
    devices = list(
        (
            await db_session.execute(
                select(TrustedDevice).where(TrustedDevice.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    next_cookies = {}
    if trust_device:
        assert len(devices) == 1
        assert devices[0].mfa_epoch == user.mfa_epoch
        trusted = verified_cookies[settings.trusted_device_cookie_name]
        assert trusted["httponly"]
        assert trusted.value
        next_cookies[settings.trusted_device_cookie_name] = trusted.value
        original_digest = devices[0].token_hash
    else:
        assert devices == []
        assert settings.trusted_device_cookie_name not in verified_cookies

    next_response = Response()
    next_pending = await coordinator.check_and_issue_challenges(
        user, _request(next_cookies), next_response, "en"
    )
    await db_session.commit()
    if trust_device:
        assert next_pending is None
        rotated = _cookies(next_response)[settings.trusted_device_cookie_name]
        assert rotated.value != trusted.value
        assert rotated["httponly"]
        await db_session.refresh(devices[0])
        assert devices[0].token_hash != original_digest
    else:
        assert next_pending is not None
        assert next_pending.methods[0].method == "email_otp"
        assert next_pending.methods[0].challenge_token != method.challenge_token
        assert next_response.status_code == 202
