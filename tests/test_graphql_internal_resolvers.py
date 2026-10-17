"""Retained GraphQL resolvers stay testable without publishing an HTTP route."""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.graphql.queries import Query
from app.models import Event, News, Schedule
from app.models.schedule import Group
from app.utils.pagination import encode_datetime_cursor


def _info(session, *, current_user=None, checker=None):
    return SimpleNamespace(
        context=SimpleNamespace(
            session=session,
            current_user=current_user,
            checker=checker,
        )
    )


@pytest.mark.asyncio
async def test_internal_news_resolver_keeps_keyset_and_id_lookup_contract(
    db_session, user_factory
):
    query = Query()
    info = _info(db_session)

    empty = await query.news(info, limit=2)
    assert empty.items == []
    assert empty.page_info.total_count == 0
    assert empty.page_info.has_next_page is False

    author = await user_factory()
    author_id = author.id
    now = dt.datetime.now(dt.UTC)
    rows = [
        News(
            title=f"News {minutes}",
            content="Body",
            author_id=author_id,
            created_at=now - dt.timedelta(minutes=minutes),
        )
        for minutes in (10, 5, 0)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    news_ids = [str(row.id) for row in rows]
    await db_session.commit()

    first = await query.news(info, limit=2)
    assert [item.title for item in first.items] == ["News 0", "News 5"]
    assert first.page_info.total_count == 3
    assert first.page_info.has_next_page is True
    assert first.page_info.has_previous_page is False
    assert first.page_info.cursor is not None

    second = await query.news(info, limit=2, after=first.page_info.cursor)
    assert [item.title for item in second.items] == ["News 10"]
    assert second.page_info.has_next_page is False
    assert second.page_info.has_previous_page is True
    assert second.page_info.cursor is None

    for invalid_cursor in (
        "not-base64-invalid!!!",
        encode_datetime_cursor(now, "invalid-uuid-tiebreaker"),
    ):
        fallback = await query.news(info, limit=2, after=invalid_cursor)
        assert [item.title for item in fallback.items] == ["News 0", "News 5"]
        assert fallback.page_info.has_previous_page is True

    found = await query.news_by_id(info, news_ids[0])
    assert found is not None
    assert found.title == "News 10"
    assert found.author is not None
    assert found.author.email is None
    assert await query.news_by_id(info, "invalid-uuid-format") is None
    assert await query.news_by_id(info, str(uuid.uuid4())) is None


@pytest.mark.asyncio
async def test_internal_events_resolver_keeps_active_filter_and_keyset_contract(
    db_session, user_factory
):
    query = Query()
    info = _info(db_session)

    empty = await query.events(info, limit=2, active_only=False)
    assert empty.items == []
    assert empty.page_info.total_count == 0

    creator = await user_factory()
    creator_id = creator.id
    now = dt.datetime.now(dt.UTC)
    rows = [
        Event(
            title=title,
            starts_at=now + dt.timedelta(minutes=offset),
            ends_at=now + dt.timedelta(minutes=offset + 30),
            created_by=creator_id,
            is_active=active,
        )
        for title, offset, active in (
            ("Earlier", -10, True),
            ("Middle", -5, False),
            ("Latest", 0, True),
        )
    ]
    db_session.add_all(rows)
    await db_session.commit()

    active_events = await query.events(info, limit=2, active_only=True)
    assert [item.title for item in active_events.items] == ["Latest", "Earlier"]
    assert active_events.page_info.total_count == 2
    assert active_events.page_info.has_next_page is False

    first = await query.events(info, limit=2, active_only=False)
    assert [item.title for item in first.items] == ["Latest", "Middle"]
    assert first.page_info.total_count == 3
    assert first.page_info.has_next_page is True
    assert first.page_info.has_previous_page is False
    assert first.page_info.cursor is not None

    second = await query.events(
        info, limit=2, active_only=False, after=first.page_info.cursor
    )
    assert [item.title for item in second.items] == ["Earlier"]
    assert second.page_info.has_previous_page is True
    assert second.page_info.has_next_page is False

    for invalid_cursor in (
        "invalid-cursor-format!!!",
        encode_datetime_cursor(now, "invalid-uuid-tiebreaker"),
    ):
        fallback = await query.events(
            info, limit=2, active_only=False, after=invalid_cursor
        )
        assert [item.title for item in fallback.items] == ["Latest", "Middle"]


@pytest.mark.asyncio
async def test_internal_schedule_resolver_keeps_fail_closed_and_allowed_behavior(
    db_session,
):
    query = Query()
    group = Group(name="CS-101")
    db_session.add(group)
    await db_session.flush()
    group_id = group.id
    entry = Schedule(
        group_id=group_id,
        weekday="monday",
        start_time=dt.datetime.now(dt.UTC),
        end_time=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        subject="Mathematics",
        lesson_type="lecture",
    )
    db_session.add(entry)
    await db_session.commit()

    checker = SimpleNamespace(check_permission=AsyncMock(return_value=True))
    actor_id = uuid.uuid4()
    info = _info(
        db_session,
        current_user=SimpleNamespace(id=actor_id),
        checker=checker,
    )
    entries = await query.schedule(info, str(group_id))
    assert len(entries) == 1
    assert entries[0].subject == "Mathematics"
    assert entries[0].day_of_week == "monday"
    checker.check_permission.assert_awaited_once_with(
        resource_type="group",
        resource_id=str(group_id),
        permission="view",
        user_id=str(actor_id),
    )

    anonymous_checker = SimpleNamespace(check_permission=AsyncMock(return_value=True))
    anonymous_entries = await query.schedule(
        _info(db_session, checker=anonymous_checker), str(group_id)
    )
    assert len(anonymous_entries) == 1
    anonymous_checker.check_permission.assert_awaited_once_with(
        resource_type="group",
        resource_id=str(group_id),
        permission="view",
        user_id="anonymous",
    )

    assert await query.schedule(info, "invalid-group-uuid-format") == []
    no_checker = await query.schedule(
        _info(db_session, current_user=SimpleNamespace(id=actor_id)), str(group_id)
    )
    assert no_checker == []


@pytest.mark.asyncio
async def test_internal_me_resolver_keeps_nullable_authenticated_user_behavior(
    db_session, user_factory
):
    query = Query()
    assert await query.me(_info(db_session)) is None

    user = await user_factory()
    result = await query.me(_info(db_session, current_user=user))
    assert result is not None
    assert result.email == user.email
