"""Unit tests for SessionRepository (app/repositories/session_repository.py).

Hermetic against the SQLite test DB (``db_session`` fixture; ``active_sessions`` is
auto-created via create_all — it is NOT partitioned). Real users come from
``user_factory``. ``created_at``/``last_seen_at`` are always set explicitly to avoid
the async server-default lazy-load trap and to make ordering deterministic.

Datetime values read back from SQLite are compared against each other (both read
through the same path) rather than against test-local ``now`` — SQLite strips the
tzinfo so a naive-vs-aware comparison would raise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActiveSession
from app.repositories.session_repository import (
    SessionRepository,
    get_session_repository,
)

# Sentinel so callers can pass an explicit ``last_seen_at=None`` (to exercise the
# "never seen" branch of cleanup_expired) without the helper defaulting it to
# ``created_at``.
_UNSET = object()


@pytest.fixture
def repo(db_session: AsyncSession) -> SessionRepository:
    return SessionRepository(db_session)


async def _add(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    jti: str,
    created_at: datetime,
    expires_at: datetime,
    last_seen_at: datetime | None | object = _UNSET,
    revoked_at: datetime | None = None,
) -> ActiveSession:
    last_seen = created_at if last_seen_at is _UNSET else last_seen_at
    session = ActiveSession(
        user_id=user_id,
        jti=jti,
        created_at=created_at,
        expires_at=expires_at,
        last_seen_at=last_seen,
        revoked_at=revoked_at,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    db.add(session)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_get_session_repository_factory_returns_instance(db_session):
    built = get_session_repository(db_session)
    assert isinstance(built, SessionRepository)
    assert built.model is ActiveSession
    assert built.dto_class.__name__ == "ActiveSessionDTO"


@pytest.mark.asyncio
async def test_get_by_jti_hit_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="jti-1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    fetched = await repo.get_by_jti("jti-1")
    assert fetched is not None
    assert fetched.jti == "jti-1"
    assert fetched.user_id == user.id
    assert await repo.get_by_jti("missing") is None


@pytest.mark.asyncio
async def test_touch_updates_last_seen(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    session = await _add(
        db_session,
        user.id,
        jti="touch",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(hours=2),
    )
    before = await repo.get_by_jti("touch")
    await repo.touch(session.id)
    after = await repo.get_by_jti("touch")
    assert before.last_seen_at is not None
    assert after.last_seen_at is not None
    assert after.last_seen_at > before.last_seen_at


@pytest.mark.asyncio
async def test_touch_by_jti_updates_last_seen(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="touch-jti",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(hours=2),
    )
    before = await repo.get_by_jti("touch-jti")
    await repo.touch_by_jti("touch-jti")
    after = await repo.get_by_jti("touch-jti")
    assert after.last_seen_at > before.last_seen_at


@pytest.mark.asyncio
async def test_get_last_seen_map_empty_and_populated(repo, db_session, user_factory):
    assert await repo.get_last_seen_map([]) == {}

    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="m1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=10),
    )
    await _add(
        db_session,
        user.id,
        jti="m2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=2),
    )
    # Revoked sessions are excluded from the aggregate.
    await _add(
        db_session,
        user.id,
        jti="m3",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now,
        revoked_at=now,
    )

    result = await repo.get_last_seen_map([user.id])
    assert user.id in result
    assert result[user.id] is not None


@pytest.fixture
async def revocation_sessions(db_session, user_factory):
    owner = await user_factory()
    other = await user_factory()
    now = datetime.now(UTC)
    sessions = {}
    for name, user_id, revoked_at in [
        ("current", owner.id, None),
        ("laptop", owner.id, None),
        ("tablet", owner.id, None),
        ("revoked", owner.id, now - timedelta(days=1)),
        ("other", other.id, None),
    ]:
        sessions[name] = await _add(
            db_session,
            user_id,
            jti=f"revoke-{name}",
            created_at=now - timedelta(days=2),
            expires_at=now + timedelta(hours=1),
            revoked_at=revoked_at,
        )
    return owner, other, sessions


async def _revocation_times(db_session):
    result = await db_session.execute(
        select(ActiveSession.id, ActiveSession.revoked_at)
    )
    return dict(result.all())


@pytest.mark.asyncio
async def test_revoke_only_owned_active_session(repo, db_session, revocation_sessions):
    owner, other, sessions = revocation_sessions
    before = await _revocation_times(db_session)
    target = sessions["laptop"].id

    assert await repo.revoke(target, other.id) is False
    assert await _revocation_times(db_session) == before
    assert await repo.revoke(target, owner.id) is True
    after = await _revocation_times(db_session)
    assert after[target] is not None
    assert {key: value for key, value in after.items() if key != target} == {
        key: value for key, value in before.items() if key != target
    }
    assert await repo.revoke(target, owner.id) is False
    assert await repo.revoke(uuid.uuid4(), owner.id) is False
    assert await _revocation_times(db_session) == after


@pytest.mark.asyncio
async def test_revoke_all_except_preserves_current_and_other_users(
    repo, db_session, revocation_sessions
):
    owner, _, sessions = revocation_sessions
    before = await _revocation_times(db_session)

    assert await repo.revoke_all_except(owner.id, sessions["current"].id) == 2

    after = await _revocation_times(db_session)
    for name in ("laptop", "tablet"):
        assert after[sessions[name].id] is not None
    for name in ("current", "revoked", "other"):
        assert after[sessions[name].id] == before[sessions[name].id]
    assert await repo.revoke_all_except(owner.id, sessions["current"].id) == 0
    assert await _revocation_times(db_session) == after


@pytest.mark.asyncio
async def test_revoke_all_for_user_preserves_other_users_and_existing_timestamp(
    repo, db_session, revocation_sessions
):
    owner, _, sessions = revocation_sessions
    before = await _revocation_times(db_session)

    assert await repo.revoke_all_for_user(owner.id) == 3

    after = await _revocation_times(db_session)
    for name in ("current", "laptop", "tablet"):
        assert after[sessions[name].id] is not None
    for name in ("revoked", "other"):
        assert after[sessions[name].id] == before[sessions[name].id]
    assert await repo.revoke_all_for_user(owner.id) == 0
    assert await _revocation_times(db_session) == after
