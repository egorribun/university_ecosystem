"""Unit tests for ActiveSessionRepository (app/repositories/active_session_repository.py).

Hermetic against the SQLite test DB (``db_session`` fixture; ``active_sessions`` is
auto-created via create_all). Real users come from ``user_factory``. ``created_at`` is
always set explicitly to avoid the async server-default lazy-load trap and to make
``ORDER BY created_at`` deterministic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActiveSession
from app.repositories.active_session_repository import ActiveSessionRepository


@pytest.fixture
def repo(db_session: AsyncSession) -> ActiveSessionRepository:
    return ActiveSessionRepository(db_session)


async def _add(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    jti: str,
    created_at: datetime,
    expires_at: datetime,
    revoked_at: datetime | None = None,
) -> ActiveSession:
    session = ActiveSession(
        user_id=user_id,
        jti=jti,
        created_at=created_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
        last_seen_at=created_at,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    db.add(session)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_create_and_get_by_jti_roundtrip_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)

    dto = await repo.create(
        {
            "user_id": user.id,
            "jti": "jti-create",
            "created_at": now,
            "expires_at": now + timedelta(hours=1),
        }
    )
    assert dto.jti == "jti-create"
    assert dto.user_id == user.id

    fetched = await repo.get_by_jti("jti-create")
    assert fetched is not None
    assert fetched.user_id == user.id
    assert await repo.get_by_jti("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_active_count_excludes_revoked_and_expired(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="active",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="revoked",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        revoked_at=now,
    )
    await _add(
        db_session,
        user.id,
        jti="expired",
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )

    assert await repo.get_active_count_for_user(user.id, now) == 1


@pytest.mark.asyncio
async def test_get_oldest_active_sessions_orders_limits_excludes(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="s1",
        created_at=now - timedelta(minutes=30),
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="s2",
        created_at=now - timedelta(minutes=20),
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="s3",
        created_at=now - timedelta(minutes=10),
        expires_at=now + timedelta(hours=1),
    )

    oldest = await repo.get_oldest_active_sessions(user.id, now, limit=2)
    assert [s.jti for s in oldest] == ["s1", "s2"]  # ascending created_at, capped at 2

    excluded = await repo.get_oldest_active_sessions(
        user.id, now, limit=5, exclude_jti="s1"
    )
    jtis = [s.jti for s in excluded]
    assert "s1" not in jtis
    assert set(jtis) == {"s2", "s3"}


@pytest.mark.asyncio
async def test_revoke_by_id_hit_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    session = await _add(
        db_session,
        user.id,
        jti="to-revoke",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    assert await repo.revoke_by_id(session.id, now) is True
    # autoflush makes the revocation visible to the count query.
    assert await repo.get_active_count_for_user(user.id, now) == 0
    assert await repo.revoke_by_id(uuid.uuid4(), now) is False


@pytest.mark.asyncio
async def test_delete_matching_returns_rowcount(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="d1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="d2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    deleted = await repo.delete_matching(ActiveSession.user_id == user.id)
    assert deleted == 2
    assert await repo.get_active_count_for_user(user.id, now) == 0


@pytest.mark.asyncio
async def test_get_active_session_with_user_join_hit_and_misses(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="join-ok",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    result = await repo.get_active_session_with_user(user.id, "join-ok")
    assert result is not None
    fetched_user, fetched_session = result
    assert fetched_user.id == user.id
    assert fetched_session.jti == "join-ok"

    # Revoked session → None.
    await _add(
        db_session,
        user.id,
        jti="join-revoked",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        revoked_at=now,
    )
    assert await repo.get_active_session_with_user(user.id, "join-revoked") is None

    # Unknown jti → None.
    assert await repo.get_active_session_with_user(user.id, "no-such-jti") is None


@pytest.mark.asyncio
async def test_get_active_session_with_user_inactive_user_returns_none(
    repo, db_session, user_factory
):
    user = await user_factory(is_active=False)
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="inactive-join",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    assert await repo.get_active_session_with_user(user.id, "inactive-join") is None


@pytest.mark.asyncio
async def test_revoke_all_except_keeps_current(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    keep = await _add(
        db_session,
        user.id,
        jti="keep",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="r1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="r2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    revoked = await repo.revoke_all_except(user.id, keep.id)
    assert revoked == 2
    assert await repo.get_active_count_for_user(user.id, now) == 1


@pytest.mark.asyncio
async def test_revoke_all_for_user_revokes_everything(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="a1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="a2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    revoked = await repo.revoke_all_for_user(user.id)
    assert revoked == 2
    assert await repo.get_active_count_for_user(user.id, now) == 0
