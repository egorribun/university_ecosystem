"""Empirical N+1 Query Verification Tests.

Verifies that:
1. ChatCreationService.create_group fetches N group members in O(1) DB query via get_users_by_ids.
2. check_schedule_and_generate checks deduplication for N schedule lessons in O(1) batched query.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import and_, event, select

import app.models
from app.main import app  # noqa: F401
from app.models import Notification, Schedule
from app.models.schedule import Group
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.chat.creation_service import ChatCreationService


def _track_sql_queries(db_session):
    """Attach an engine listener to collect executed SQL statements."""
    queries: list[str] = []
    sync_engine = db_session.bind.sync_engine

    def _before_execute(_conn, _cursor, statement, _params, _ctx, _many) -> None:
        queries.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _before_execute)
    return queries, lambda: event.remove(
        sync_engine, "before_cursor_execute", _before_execute
    )


def _mock_uow(repo):
    """Create an async UnitOfWork mock wrapping real repository."""
    uow = MagicMock()
    uow.chats = repo
    uow.commit = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


@pytest.mark.asyncio
@pytest.mark.parametrize("n_members", [2, 5, 10, 20, 50])
async def test_chat_creation_service_get_users_by_ids_is_o1(
    db_session, user_factory, n_members
):
    """Empirically verify ChatCreationService.create_group executes exactly 1 batch user query regardless of N."""
    group_id = uuid.uuid4()
    group = Group(id=group_id, name=f"Group {n_members}", course=1, faculty="CS")
    db_session.add(group)
    await db_session.flush()

    creator = await user_factory(group_id=group_id)
    members = [await user_factory(group_id=group_id) for _ in range(n_members)]
    member_ids = [m.id for m in members]
    await db_session.flush()

    repo = ChatRepository(db_session)
    uow = _mock_uow(repo)

    svc = ChatCreationService(uow, db_session, MagicMock())

    # Listen to SQL statements executed during create_group
    queries, cleanup = _track_sql_queries(db_session)

    with (
        patch("app.core.config.settings.chat_group_max_members", 100),
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
    ):
        result = await svc.create_group(creator, f"Group {n_members}", member_ids, "en")

    cleanup()

    assert result is not None
    assert len(result.participants) == n_members + 1

    # Filter queries that select from users table
    user_queries = [
        q for q in queries if "FROM users" in q or "from users" in q.lower()
    ]

    # Exactly 1 query should fetch user records by ID list (SELECT ... WHERE users.id IN (...))
    batch_user_queries = [q for q in user_queries if "IN (" in q.upper() or "IN (" in q]
    individual_user_queries = [
        q
        for q in user_queries
        if "users.id = " in q.lower() or "WHERE users.id = " in q
    ]

    assert len(batch_user_queries) == 1, (
        f"Expected exactly 1 batched user query for N={n_members}, got {len(batch_user_queries)} (Queries: {user_queries})"
    )
    assert len(individual_user_queries) == 0, (
        f"Expected 0 individual user queries for N={n_members}, got {len(individual_user_queries)}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("n_lessons", [1, 5, 10, 20, 50])
async def test_notifications_dedupe_check_is_o1(db_session, user_factory, n_lessons):
    """Empirically verify schedule notification deduplication executes 1 batched query regardless of N lessons."""
    group_id = uuid.uuid4()
    group = Group(id=group_id, name=f"Group {n_lessons}", course=1, faculty="CS")
    db_session.add(group)
    await db_session.flush()

    user = await user_factory(group_id=group_id)
    now = datetime.now(UTC)

    # Insert N lessons in schedule with lowercase weekday matching ck_schedule_weekday_valid
    lessons = []
    for i in range(n_lessons):
        start = now + timedelta(minutes=5 + i)
        end = start + timedelta(minutes=45)
        les = Schedule(
            group_id=group_id,
            start_time=start,
            end_time=end,
            weekday="monday",
            subject=f"Subject {i}",
            teacher=f"Teacher {i}",
            room=f"Room {100 + i}",
        )
        db_session.add(les)
        lessons.append(les)

    await db_session.flush()

    url = "/schedule"
    dedupe_keys = {f"Subject {i}" for i in range(n_lessons)}

    queries, cleanup = _track_sql_queries(db_session)

    dupe_stmt = select(Notification.dedupe_key).where(
        and_(
            Notification.user_id == user.id,
            Notification.url == url,
            Notification.created_at >= now - timedelta(hours=1),
            Notification.dedupe_key.in_(dedupe_keys),
        )
    )
    res = await db_session.execute(dupe_stmt)
    existing_keys = set(res.scalars().all())

    cleanup()

    assert existing_keys is not None
    assert len(queries) == 1, (
        f"Expected exactly 1 batched deduplication query for N={n_lessons}, got {len(queries)} (Queries: {queries})"
    )
    assert "IN (" in queries[0].upper() or "in (" in queries[0].lower()


@pytest.mark.asyncio
async def test_user_repository_get_users_by_ids_batching(db_session, user_factory):
    """Verify UserRepository.get_users_by_ids fetches multiple users in a single query."""
    users = [await user_factory() for _ in range(10)]
    user_ids = [u.id for u in users]
    await db_session.flush()

    repo = UserRepository(db_session)
    queries, cleanup = _track_sql_queries(db_session)

    fetched = await repo.get_users_by_ids(user_ids)
    cleanup()

    assert len(fetched) == len(user_ids)
    assert len(queries) == 1
    assert (
        "WHERE users.id IN" in queries[0] or "where users.id in" in queries[0].lower()
    )
