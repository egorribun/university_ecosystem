import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth import constants


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
async def mfa_challenge_factory(db_session: AsyncSession):
    async def _factory(
        user: models.User,
        challenge_type: str = constants.CHALLENGE_TYPE_TOTP_VERIFY,
        expires_delta: int = 5,
    ):
        token = uuid.uuid4().hex
        challenge = models.MfaChallenge(
            user_id=user.id,
            challenge_type=challenge_type,
            token=token,
            expires_at=datetime.now(UTC) + timedelta(minutes=expires_delta),
            state=models.ChallengeState.PENDING,
            created_at=datetime.now(UTC),
        )
        db_session.add(challenge)
        await db_session.commit()
        await db_session.refresh(challenge)
        return challenge

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
