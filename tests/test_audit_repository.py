"""Unit tests for AuditRepository (app/repositories/audit_repository.py).

Hermetic against the SQLite test DB. ``data_access_logs`` is created via a hand-written
DDL (excluded from create_all) — tests stay within those columns. Real users come from
``user_factory`` so the actor/subject FK values are valid. ``created_at`` is set
explicitly on every entry (deterministic ``ORDER BY`` + avoids the async server-default
lazy-load trap).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repository import AuditRepository


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> AuditRepository:
    return AuditRepository(db_session)


@pytest.mark.asyncio
async def test_get_logs_by_user_matches_actor_or_subject_desc(audit_repo, user_factory):
    ua = await user_factory()
    ub = await user_factory()
    base = datetime.now(UTC)
    await audit_repo.batch_create(
        [
            {
                "actor_user_id": ua.id,
                "resource_type": "user",
                "action": "view",
                "created_at": base - timedelta(minutes=3),
            },
            {
                "subject_user_id": ua.id,
                "resource_type": "user",
                "action": "edit",
                "created_at": base - timedelta(minutes=1),
            },
            {
                "actor_user_id": ub.id,
                "resource_type": "event",
                "action": "view",
                "created_at": base - timedelta(minutes=2),
            },
        ]
    )

    logs = await audit_repo.get_logs_by_user(ua.id)
    assert len(logs) == 2  # ua matched as actor (row1) and as subject (row2)
    assert logs[0].action == "edit"  # newest first (DESC)
    assert logs[1].action == "view"

    limited = await audit_repo.get_logs_by_user(ua.id, limit=1)
    assert len(limited) == 1
    assert limited[0].action == "edit"


@pytest.mark.asyncio
async def test_list_logs_filters_pagination_and_limit_cap(audit_repo, user_factory):
    ua = await user_factory()
    ub = await user_factory()
    base = datetime.now(UTC)
    await audit_repo.batch_create(
        [
            {
                "actor_user_id": ua.id,
                "resource_type": "user",
                "action": "a1",
                "created_at": base - timedelta(minutes=4),
            },
            {
                "actor_user_id": ua.id,
                "resource_type": "event",
                "action": "a2",
                "created_at": base - timedelta(minutes=3),
            },
            {
                "actor_user_id": ub.id,
                "resource_type": "user",
                "action": "b1",
                "created_at": base - timedelta(minutes=2),
            },
            {
                "subject_user_id": ua.id,
                "resource_type": "user",
                "action": "s1",
                "created_at": base - timedelta(minutes=1),
            },
        ]
    )

    by_actor = await audit_repo.list_logs(actor_id=ua.id)
    assert {r.action for r in by_actor} == {"a1", "a2"}

    by_subject = await audit_repo.list_logs(subject_id=ua.id)
    assert {r.action for r in by_subject} == {"s1"}

    by_type = await audit_repo.list_logs(resource_type="user")
    assert {r.action for r in by_type} == {"a1", "b1", "s1"}

    page = await audit_repo.list_logs(limit=2, offset=0)
    assert len(page) == 2
    page2 = await audit_repo.list_logs(limit=2, offset=2)
    assert len(page2) == 2

    # limit > 1000 exercises the `min(limit, 1000)` cap without error.
    capped = await audit_repo.list_logs(limit=5000)
    assert len(capped) == 4


@pytest.mark.asyncio
async def test_prune_logs_deletes_only_older_than_cutoff(audit_repo, user_factory):
    ua = await user_factory()
    now = datetime.now(UTC)
    await audit_repo.batch_create(
        [
            {
                "actor_user_id": ua.id,
                "resource_type": "user",
                "action": "old",
                "created_at": now - timedelta(days=40),
            },
            {
                "actor_user_id": ua.id,
                "resource_type": "user",
                "action": "new",
                "created_at": now - timedelta(days=1),
            },
        ]
    )

    deleted = await audit_repo.prune_logs(now - timedelta(days=30))
    assert deleted == 1

    remaining = await audit_repo.list_logs(actor_id=ua.id)
    assert [r.action for r in remaining] == ["new"]
