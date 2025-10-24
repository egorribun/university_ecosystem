import datetime as dt

import pytest
from sqlalchemy import select

from app.auth import mfa
from app.core.database import async_session
from app.models.models import ActiveSession, MfaChallenge, User
from app.services.session_cleanup import cleanup_expired_sessions


@pytest.mark.anyio
async def test_cleanup_expired_sessions_removes_expired(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="cleanup@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired = ActiveSession(
        user_id=user.id,
        jti="expired",
        expires_at=now - dt.timedelta(minutes=5),
    )
    revoked = ActiveSession(
        user_id=user.id,
        jti="revoked",
        expires_at=now + dt.timedelta(hours=1),
        revoked_at=now - dt.timedelta(minutes=2),
    )
    active = ActiveSession(
        user_id=user.id,
        jti="active",
        expires_at=now + dt.timedelta(hours=2),
    )
    future_revocation = ActiveSession(
        user_id=user.id,
        jti="revoked-future",
        expires_at=now + dt.timedelta(hours=2),
        revoked_at=now + dt.timedelta(hours=1),
    )

    db_session.add_all([expired, revoked, active, future_revocation])
    await db_session.commit()

    removed = await cleanup_expired_sessions(now=now)
    assert removed == 2

    result = await db_session.execute(select(ActiveSession.jti))
    remaining = {row[0] for row in result}
    assert remaining == {"active", "revoked-future"}


@pytest.mark.anyio
async def test_cleanup_expired_sessions_removes_mfa_challenges(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="cascade@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired_session = ActiveSession(
        user_id=user.id,
        jti="expired-mfa",
        expires_at=now - dt.timedelta(minutes=1),
    )
    db_session.add(expired_session)
    await db_session.flush()

    challenge = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        session_id=expired_session.id,
        challenge_type=mfa.CHALLENGE_TYPE_TOTP_VERIFY,
    )
    await db_session.commit()

    removed = await cleanup_expired_sessions(now=now)

    assert removed == 1

    async with async_session() as verify_session:
        result = await verify_session.execute(
            select(MfaChallenge).where(MfaChallenge.id == challenge.id)
        )
        assert result.scalars().first() is None
