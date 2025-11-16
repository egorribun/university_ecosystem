import datetime as dt

import pytest
from sqlalchemy import select

from app.models.models import MfaChallenge, User
from app.services.mfa_challenge_cleanup import cleanup_stale_mfa_challenges


@pytest.mark.anyio
async def test_cleanup_stale_mfa_challenges_respects_grace_period(db_session):
    now = dt.datetime.now(dt.UTC)
    grace_seconds = 600
    cutoff = now - dt.timedelta(seconds=grace_seconds)

    user = User(email="mfa-cleanup@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired_old = MfaChallenge(
        user_id=user.id,
        challenge_type="totp",
        token="expired-old",
        expires_at=cutoff - dt.timedelta(seconds=5),
    )
    expired_recent = MfaChallenge(
        user_id=user.id,
        challenge_type="totp",
        token="expired-recent",
        expires_at=cutoff + dt.timedelta(seconds=15),
    )
    consumed_old = MfaChallenge(
        user_id=user.id,
        challenge_type="totp",
        token="consumed-old",
        expires_at=cutoff - dt.timedelta(seconds=30),
        consumed_at=cutoff - dt.timedelta(seconds=10),
    )
    consumed_recent = MfaChallenge(
        user_id=user.id,
        challenge_type="totp",
        token="consumed-recent",
        expires_at=cutoff - dt.timedelta(seconds=30),
        consumed_at=cutoff + dt.timedelta(seconds=30),
    )
    future_active = MfaChallenge(
        user_id=user.id,
        challenge_type="totp",
        token="future-active",
        expires_at=now + dt.timedelta(minutes=5),
    )

    db_session.add_all(
        [
            expired_old,
            expired_recent,
            consumed_old,
            consumed_recent,
            future_active,
        ]
    )
    await db_session.commit()

    deleted = await cleanup_stale_mfa_challenges(
        db=db_session, grace_period_seconds=grace_seconds, now=now
    )

    assert deleted == 2

    remaining = await db_session.execute(select(MfaChallenge.token))
    assert set(remaining.scalars().all()) == {
        "expired-recent",
        "consumed-recent",
        "future-active",
    }
