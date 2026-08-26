from datetime import UTC, datetime
from types import SimpleNamespace

import pyotp
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth import constants, mfa
from app.core.fingerprint import extract_request_fingerprint


@pytest_asyncio.fixture
async def mfa_totp_enrollment_factory(db_session: AsyncSession):
    async def _factory(user: models.User, secret: str | None = None):
        if secret is None:
            secret = pyotp.random_base32()

        enrollment = models.MfaTotpEnrollment(
            user_id=user.id,
            secret=secret,
            is_active=True,
            confirmed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db_session.add(enrollment)
        await db_session.commit()
        await db_session.refresh(enrollment)
        return enrollment, secret

    return _factory


@pytest_asyncio.fixture
async def mfa_challenge_factory(db_session: AsyncSession, async_client):
    async def _factory(
        user: models.User,
        challenge_type: str = constants.CHALLENGE_TYPE_TOTP_VERIFY,
        expires_delta: int = 5,
    ):
        session_identifier = "mfa-race-preauth"
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": async_client.headers["user-agent"]},
        )
        issued = await mfa.issue_challenge(
            db_session,
            user_id=user.id,
            challenge_type=challenge_type,
            ttl_seconds=expires_delta * 60,
            flow="login",
            session_identifier=session_identifier,
            client_fingerprint=extract_request_fingerprint(request),
            method=constants.MFA_METHOD_TOTP,
        )
        await db_session.commit()
        async_client.cookies.set("mfa_pre_auth_v1", session_identifier, path="/")
        return SimpleNamespace(
            token=issued.challenge_token,
            challenge=issued.challenge,
        )

    return _factory


@pytest_asyncio.fixture
async def user_with_totp(user_factory, mfa_totp_enrollment_factory):
    user = await user_factory()
    _enrollment, secret = await mfa_totp_enrollment_factory(user)
    # Attach secret to user object temporarily for easy access in tests
    user._totp_secret = secret
    return user


@pytest_asyncio.fixture
async def test_mfa_challenge(user_with_totp, mfa_challenge_factory):
    return await mfa_challenge_factory(user_with_totp)
