import datetime as dt

import pytest
from sqlalchemy import event, select

from app.auth import mfa
from app.core.database import async_session, engine
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

    statements: list[str] = []

    def record_sql(
        conn, cursor, statement, parameters, context, executemany
    ):  # pragma: no cover - signature defined by SQLAlchemy
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
    try:
        removed = await cleanup_expired_sessions(now=now)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_sql)

    assert removed == 1

    delete_statements = [
        stmt for stmt in statements if stmt.lstrip().upper().startswith("DELETE")
    ]
    assert len(delete_statements) == 2

    async with async_session() as verify_session:
        result = await verify_session.execute(
            select(MfaChallenge).where(MfaChallenge.id == challenge.id)
        )
        assert result.scalars().first() is None


@pytest.mark.anyio
async def test_cleanup_expired_sessions_handles_large_batches(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="bulk@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired_sessions = [
        ActiveSession(
            user_id=user.id,
            jti=f"expired-{idx}",
            expires_at=now - dt.timedelta(minutes=idx + 1),
        )
        for idx in range(300)
    ]
    revoked_sessions = [
        ActiveSession(
            user_id=user.id,
            jti=f"revoked-{idx}",
            expires_at=now + dt.timedelta(hours=1),
            revoked_at=now - dt.timedelta(minutes=idx + 1),
        )
        for idx in range(150)
    ]
    active_sessions = [
        ActiveSession(
            user_id=user.id,
            jti=f"active-{idx}",
            expires_at=now + dt.timedelta(hours=2),
        )
        for idx in range(50)
    ]

    db_session.add_all(expired_sessions + revoked_sessions + active_sessions)
    await db_session.flush()

    active_ids = {session.id for session in active_sessions}

    challenge_targets = expired_sessions[:180] + revoked_sessions[:40]
    db_session.add_all(
        [
            MfaChallenge(
                user_id=user.id,
                session_id=session.id,
                challenge_type=mfa.CHALLENGE_TYPE_TOTP_VERIFY,
                token=f"token-{session.id}",
                expires_at=now + dt.timedelta(minutes=5),
            )
            for session in challenge_targets
        ]
    )
    await db_session.commit()

    removed = await cleanup_expired_sessions(now=now)

    assert removed == len(expired_sessions) + len(revoked_sessions)

    remaining_sessions = await db_session.execute(select(ActiveSession.id))
    assert set(remaining_sessions.scalars().all()) == active_ids

    remaining_challenges = await db_session.execute(select(MfaChallenge.id))
    assert remaining_challenges.scalars().all() == []
