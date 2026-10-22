from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.auth.mfa.email_otp import EmailOtpService
from app.core import database
from app.models import ChallengeState, MfaChallenge, User
from app.services.auth.mfa_coordinator import MfaCoordinator


@pytest.fixture
def coordinator():
    uow = AsyncMock()
    repo = AsyncMock()
    return MfaCoordinator(uow, repo)


def _request() -> MagicMock:
    request = MagicMock()
    request.cookies = {}
    request.headers = {}
    return request


@pytest.mark.asyncio
async def test_check_and_issue_challenges_no_mfa(coordinator):
    user = MagicMock(id=uuid4(), mfa_required=False)
    coordinator.repo.has_active_mfa.return_value = False

    res = await coordinator.check_and_issue_challenges(user, _request(), None, "en")
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
    user = MagicMock(id=uuid4(), mfa_required=True)
    with pytest.raises(HTTPException) as exc:
        await coordinator.check_and_issue_challenges(user, _request(), None, "en")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._resolve_mfa_capabilities",
    return_value={"totp": True},
)
@patch(
    "app.services.auth.mfa_coordinator.MfaCoordinator._collect_mfa_challenges",
    return_value=[
        auth_schemas.MfaMethodChallengeOut(
            method=mfa.MFA_METHOD_TOTP,
            challenge_token="token_totp",
            challenge_expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ],
)
async def test_check_and_issue_challenges_with_response(
    mock_collect, mock_resolve, coordinator
):
    user_id = uuid4()
    user = MagicMock(id=user_id, mfa_required=True, mfa_default_method=None)
    response = MagicMock(spec=Response)

    res = await coordinator.check_and_issue_challenges(user, _request(), response, "en")
    assert response.status_code == 202
    assert res.user_id == user_id
    assert res.default_method == mfa.MFA_METHOD_TOTP
    assert res.methods[0].method == mfa.MFA_METHOD_TOTP
    coordinator.uow.commit.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.auth.mfa.start_totp_verification", new_callable=AsyncMock)
@patch("app.auth.mfa.describe_challenge_attempts", return_value=(1, 5, 4))
async def test_collect_mfa_challenges_totp(mock_describe, mock_start, coordinator):
    user = MagicMock(id=uuid4())
    challenge = MagicMock(attempt_count=1, revision=1)
    mock_start.return_value = SimpleNamespace(
        challenge=challenge,
        challenge_token="token_totp",
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    capabilities = {mfa.MFA_METHOD_TOTP: True}

    methods = await coordinator._collect_mfa_challenges(user, "en", capabilities, None)

    assert len(methods) == 1
    assert methods[0].method == mfa.MFA_METHOD_TOTP
    assert methods[0].challenge_token == "token_totp"
    assert methods[0].remaining_attempts == 4


class RecordingRateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def enforce(self, *, action: str, identifier: str) -> None:
        self.calls.append((action, identifier))


@pytest.mark.asyncio
async def test_email_login_challenges_keep_distinct_client_rate_limit_buckets(
    coordinator: MfaCoordinator,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await user_factory(email_mfa_enabled_at=datetime.now(UTC), mfa_epoch=0)
    limiter = RecordingRateLimiter()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=limiter,
    )
    coordinator.repo.db = db_session
    coordinator.email_otp_service = service
    client_ips = ("203.0.113.10", "198.51.100.20")

    for index, client_ip in enumerate(client_ips):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/mfa/challenge",
                "query_string": b"",
                "headers": [(b"user-agent", b"mfa-ip-bucket-test")],
                "client": (client_ip, 12345),
            }
        )
        challenges = await coordinator._collect_mfa_challenges(
            user,
            "en",
            {mfa.MFA_METHOD_EMAIL_OTP: True},
            request=request,
            session_identifier=f"login-session-{index}",
        )
        assert len(challenges) == 1
        assert challenges[0].method == mfa.MFA_METHOD_EMAIL_OTP

    await db_session.commit()
    async with database.async_session() as reader:
        persisted = (
            (
                await reader.execute(
                    select(MfaChallenge).where(MfaChallenge.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(persisted) == 2
        assert all(challenge.state == ChallengeState.PENDING for challenge in persisted)

    assert limiter.calls == [
        ("issue", f"user:{user.id}"),
        ("issue", f"ip:{client_ips[0]}"),
        ("issue", f"user:{user.id}"),
        ("issue", f"ip:{client_ips[1]}"),
    ]
