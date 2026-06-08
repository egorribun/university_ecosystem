"""Unit tests for NotificationRepository (app/repositories/notification_repository.py).

Hermetic against the SQLite test DB. ``notifications`` is RANGE-partitioned by
``created_at`` on PostgreSQL (the CI integration tier), so every seed row uses a
recent ``created_at`` window (minutes from now) to land in a valid partition there;
on SQLite the table is a flat composite-PK ``(id, created_at)`` created by the
conftest DDL. Real users come from ``user_factory`` (FK on ``user_id``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification
from app.repositories.notification_repository import (
    NotificationRepository,
    get_notification_repository,
)


@pytest.fixture
def repo(db_session: AsyncSession) -> NotificationRepository:
    return NotificationRepository(db_session)


async def _add_notif(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    created_at: datetime,
    read: bool = False,
    type: str | None = None,
    dedupe_key: str | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        title=title,
        created_at=created_at,
        read=read,
        type=type,
        dedupe_key=dedupe_key,
    )
    db.add(notif)
    await db.flush()
    return notif


@pytest.mark.asyncio
async def test_get_notification_repository_factory_returns_instance(db_session):
    built = get_notification_repository(db_session)
    assert isinstance(built, NotificationRepository)
    assert built.model is Notification
    assert built.dto_class.__name__ == "NotificationDTO"


@pytest.mark.asyncio
async def test_get_for_user_orders_paginates_and_unread_filter(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(
        db_session,
        user.id,
        title="old",
        created_at=now - timedelta(minutes=10),
        read=True,
    )
    await _add_notif(
        db_session,
        user.id,
        title="mid",
        created_at=now - timedelta(minutes=5),
        read=False,
    )
    await _add_notif(
        db_session,
        user.id,
        title="new",
        created_at=now - timedelta(minutes=1),
        read=False,
    )

    rows = await repo.get_for_user(user.id)
    assert [n.title for n in rows] == ["new", "mid", "old"]  # created_at DESC

    unread = await repo.get_for_user(user.id, unread_only=True)
    assert {n.title for n in unread} == {"new", "mid"}

    page = await repo.get_for_user(user.id, skip=1, limit=1)
    assert [n.title for n in page] == ["mid"]


@pytest.mark.asyncio
async def test_get_for_user_excludes_other_users(repo, db_session, user_factory):
    user = await user_factory()
    other = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(db_session, user.id, title="mine", created_at=now)
    await _add_notif(db_session, other.id, title="theirs", created_at=now)
    rows = await repo.get_for_user(user.id)
    assert [n.title for n in rows] == ["mine"]


@pytest.mark.asyncio
async def test_get_unread_for_user_delegates(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(db_session, user.id, title="unread", created_at=now, read=False)
    await _add_notif(
        db_session,
        user.id,
        title="read",
        created_at=now - timedelta(minutes=1),
        read=True,
    )
    rows = await repo.get_unread_for_user(user.id)
    assert [n.title for n in rows] == ["unread"]


@pytest.mark.asyncio
async def test_count_unread(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(db_session, user.id, title="a", created_at=now, read=False)
    await _add_notif(
        db_session,
        user.id,
        title="b",
        created_at=now - timedelta(minutes=1),
        read=False,
    )
    await _add_notif(
        db_session, user.id, title="c", created_at=now - timedelta(minutes=2), read=True
    )
    assert await repo.count_unread(user.id) == 2
    assert await repo.count_unread(uuid.uuid4()) == 0


@pytest.mark.asyncio
async def test_mark_as_read_empty_subset_and_wrong_user(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    # Empty id list short-circuits to 0 without a query.
    assert await repo.mark_as_read([], user.id) == 0

    n1 = await _add_notif(db_session, user.id, title="m1", created_at=now, read=False)
    n2 = await _add_notif(
        db_session,
        user.id,
        title="m2",
        created_at=now - timedelta(minutes=1),
        read=False,
    )

    updated = await repo.mark_as_read([n1.id], user.id)
    assert updated == 1
    assert await repo.count_unread(user.id) == 1

    # Marking an already-read notification again → 0.
    assert await repo.mark_as_read([n1.id], user.id) == 0
    # Marking another user's notification → 0 (still unread for the owner).
    assert await repo.mark_as_read([n2.id], uuid.uuid4()) == 0
    assert await repo.count_unread(user.id) == 1


@pytest.mark.asyncio
async def test_mark_all_as_read(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(db_session, user.id, title="x", created_at=now, read=False)
    await _add_notif(
        db_session,
        user.id,
        title="y",
        created_at=now - timedelta(minutes=1),
        read=False,
    )
    assert await repo.mark_all_as_read(user.id) == 2
    assert await repo.count_unread(user.id) == 0
    # Idempotent — nothing left unread.
    assert await repo.mark_all_as_read(user.id) == 0


@pytest.mark.asyncio
async def test_get_by_dedupe_key_hit_and_miss(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(
        db_session, user.id, title="d", created_at=now, dedupe_key="dedupe-1"
    )
    found = await repo.get_by_dedupe_key(user.id, "dedupe-1")
    assert found is not None
    assert found.dedupe_key == "dedupe-1"
    assert await repo.get_by_dedupe_key(user.id, "no-such-key") is None


@pytest.mark.asyncio
async def test_count_by_type_groups_and_maps_none_to_unknown(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    await _add_notif(db_session, user.id, title="t1", created_at=now, type="chat")
    await _add_notif(
        db_session,
        user.id,
        title="t2",
        created_at=now - timedelta(minutes=1),
        type="chat",
    )
    await _add_notif(
        db_session,
        user.id,
        title="t3",
        created_at=now - timedelta(minutes=2),
        type=None,
    )
    counts = await repo.count_by_type(user.id)
    assert counts.get("chat") == 2
    assert counts.get("unknown") == 1
