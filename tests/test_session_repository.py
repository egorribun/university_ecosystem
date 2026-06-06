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
async def test_get_active_for_user_orders_by_last_seen_excludes_revoked(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="older",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=30),
    )
    await _add(
        db_session,
        user.id,
        jti="newer",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=5),
    )
    await _add(
        db_session,
        user.id,
        jti="revoked",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now,
        revoked_at=now,
    )

    sessions = await repo.get_active_for_user(user.id)
    # ORDER BY last_seen_at DESC, revoked excluded.
    assert [s.jti for s in sessions] == ["newer", "older"]


@pytest.mark.asyncio
async def test_get_active_for_user_respects_skip_and_limit(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    for i in range(3):
        await _add(
            db_session,
            user.id,
            jti=f"s{i}",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=i),
        )
    # last_seen DESC → s0 (now-0), s1 (now-1), s2 (now-2). skip=1, limit=1 → s1.
    page = await repo.get_active_for_user(user.id, skip=1, limit=1)
    assert [s.jti for s in page] == ["s1"]


@pytest.mark.asyncio
async def test_count_active_for_user_excludes_revoked_and_other_users(
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
    assert await repo.count_active_for_user(user.id) == 1
    assert await repo.count_active_for_user(uuid.uuid4()) == 0


@pytest.mark.asyncio
async def test_revoke_hit_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    session = await _add(
        db_session,
        user.id,
        jti="revoke-me",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )

    assert await repo.revoke(session.id, user.id) is True
    assert await repo.count_active_for_user(user.id) == 0
    # Already revoked → False.
    assert await repo.revoke(session.id, user.id) is False
    # Wrong user → False.
    other = await _add(
        db_session,
        user.id,
        jti="other",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    assert await repo.revoke(other.id, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_revoke_by_jti_hit_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="by-jti",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    assert await repo.revoke_by_jti("by-jti") is True
    assert await repo.revoke_by_jti("by-jti") is False  # already revoked
    assert await repo.revoke_by_jti("no-such-jti") is False


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
    assert await repo.count_active_for_user(user.id) == 1


@pytest.mark.asyncio
async def test_revoke_all_for_user(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add(
        db_session,
        user.id,
        jti="z1",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await _add(
        db_session,
        user.id,
        jti="z2",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    assert await repo.revoke_all_for_user(user.id) == 2
    assert await repo.count_active_for_user(user.id) == 0


@pytest.mark.asyncio
async def test_cleanup_expired_deletes_dormant_preserves_active(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    old = now - timedelta(days=40)
    # Dormant: old created + old last_seen → deleted.
    await _add(
        db_session,
        user.id,
        jti="dormant",
        created_at=old,
        expires_at=old + timedelta(hours=1),
        last_seen_at=old,
    )
    # Never seen + old created → deleted.
    await _add(
        db_session,
        user.id,
        jti="never-seen",
        created_at=old,
        expires_at=old + timedelta(hours=1),
        last_seen_at=None,
    )
    # Old created but recently seen ("trusted device") → preserved (RZ-TD-5).
    await _add(
        db_session,
        user.id,
        jti="long-lived",
        created_at=old,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now,
    )
    # Recent → preserved.
    await _add(
        db_session,
        user.id,
        jti="recent",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now,
    )

    deleted = await repo.cleanup_expired(max_age_days=30)
    assert deleted == 2
    remaining = {s.jti for s in await repo.get_active_for_user(user.id)}
    assert remaining == {"long-lived", "recent"}


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
