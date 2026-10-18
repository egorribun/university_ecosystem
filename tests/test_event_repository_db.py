"""Real-DB tests for EventRepository registration / attendance / file / search methods.

The existing ``test_event_repository_coverage.py`` exercises the list/search paths
against a mocked session. This file complements it with the attendance lifecycle,
event-file URLs, ``get_event_with_details``, and the non-full-text ``search_events``
filter branches (event_type / location / is_active / cursor) — all clearer to assert
against the real SQLite ``db_session``. ``events`` / ``event_attendance`` / ``event_files``
are created via the conftest DDL. ``search_events(search_query=...)`` is NOT exercised
here: it builds PostgreSQL-only ``plainto_tsquery`` / ``ts_rank`` expressions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.models import Event
from app.repositories.event_repository import EventRepository


@pytest.fixture
def event_repo_db(db_session: AsyncSession) -> EventRepository:
    return EventRepository(db_session)


async def _add_event(
    db: AsyncSession,
    created_by: uuid.UUID,
    *,
    title: str = "Event",
    event_type: str | None = None,
    location: str | None = None,
    starts_in_hours: int = 1,
    duration_hours: int = 2,
    created_at: datetime | None = None,
) -> Event:
    now = datetime.now(UTC)
    starts = now + timedelta(hours=starts_in_hours)
    event = Event(
        title=title,
        event_type=event_type,
        location=location,
        starts_at=starts,
        ends_at=starts + timedelta(hours=duration_hours),
        created_by=created_by,
        is_active=True,
        created_at=created_at or now,
    )
    db.add(event)
    await db.flush()
    return event


@pytest.mark.asyncio
async def test_search_by_title(event_repo_db, db_session, user_factory):
    user = await user_factory()
    await _add_event(db_session, user.id, title="Workshop on Rust")
    results = await event_repo_db.search("workshop")
    assert any(e.title == "Workshop on Rust" for e in results)
    assert await event_repo_db.search("no-such-event") == []


@pytest.mark.asyncio
async def test_attendance_lifecycle(event_repo_db, db_session, user_factory):
    user = await user_factory()
    event = await _add_event(db_session, user.id)

    assert await event_repo_db.get_attendance(event.id, user.id) is None

    created = await event_repo_db.create_attendance(
        event_id=event.id, user_id=user.id, qr_secret="secret", qr_hmac="hmac"
    )
    assert created is not None

    got = await event_repo_db.get_attendance(event.id, user.id)
    assert got is not None

    attended = await event_repo_db.list_user_attended_events(
        user.id,
        limit=2,
        locale="en",
    )
    assert any(
        row.id == event.id and attendance.user_id == user.id and count == 1
        for row, attendance, count in attended
    )

    deleted = await event_repo_db.delete_attendance(event.id, user.id)
    assert deleted is True
    assert await event_repo_db.get_attendance(event.id, user.id) is None


@pytest.mark.asyncio
async def test_update_attendance(event_repo_db, db_session, user_factory):
    # Isolated test: update_attendance uses RETURNING, supported on SQLite 3.35+.
    user = await user_factory()
    event = await _add_event(db_session, user.id)
    await event_repo_db.create_attendance(
        event_id=event.id, user_id=user.id, qr_secret="s", qr_hmac="h"
    )
    updated = await event_repo_db.update_attendance(
        event.id, user.id, {"qr_hmac": "h2"}
    )
    assert updated is not None
    # Missing attendance → None.
    assert (
        await event_repo_db.update_attendance(event.id, uuid.uuid4(), {"qr_hmac": "x"})
        is None
    )


@pytest.mark.asyncio
async def test_event_file_urls_and_delete(event_repo_db, db_session, user_factory):
    user = await user_factory()
    event = await _add_event(db_session, user.id)
    event_file = models.EventFile(
        event_id=event.id, file_url="http://example.com/file.pdf"
    )
    db_session.add(event_file)
    await db_session.flush()

    files = await event_repo_db.get_event_files(event.id)
    assert len(files) == 1
    assert files[0].id == event_file.id
    assert files[0].event_id == event.id

    urls = await event_repo_db.get_event_file_urls(event.id)
    assert "http://example.com/file.pdf" in urls

    await event_repo_db.delete_event_files(event.id)
    await db_session.flush()
    assert await event_repo_db.get_event_file_urls(event.id) == []


@pytest.mark.asyncio
async def test_get_event_with_details(event_repo_db, db_session, user_factory):
    user = await user_factory()
    event = await _add_event(db_session, user.id)
    await event_repo_db.create_attendance(
        event_id=event.id, user_id=user.id, qr_secret="s", qr_hmac="h"
    )

    result = await event_repo_db.get_event_with_details(event.id, user.id)
    assert result is not None
    assert result.event.id == event.id
    assert result.participant_count >= 1
    assert result.user_attendance is not None

    # Missing event → None.
    assert await event_repo_db.get_event_with_details(uuid.uuid4(), user.id) is None


@pytest.mark.asyncio
async def test_search_events_filter_branches(event_repo_db, db_session, user_factory):
    user = await user_factory()
    await _add_event(
        db_session, user.id, title="Conf", event_type="conference", location="Hall A"
    )

    by_type = await event_repo_db.search_events(event_type="confer")
    assert any(r.event.event_type == "conference" for r in by_type)

    by_loc = await event_repo_db.search_events(location="Hall")
    assert len(by_loc) >= 1

    # is_active=False → only past events; the future event is excluded.
    inactive = await event_repo_db.search_events(is_active=False)
    assert isinstance(inactive, list)

    # cursor branch.
    cursored = await event_repo_db.search_events(
        cursor=(datetime.now(UTC) - timedelta(hours=1), uuid.uuid4())
    )
    assert isinstance(cursored, list)


@pytest.mark.asyncio
async def test_manually_hidden_event_is_excluded_from_listing_and_total(
    event_repo_db, db_session, user_factory
):
    """AUD-016: is_active is the manual hide flag; hidden events are neither listed nor counted."""
    user = await user_factory()
    visible = await _add_event(db_session, user.id, title="Visible")
    hidden = await _add_event(db_session, user.id, title="Hidden")
    hidden.is_active = False
    await db_session.flush()

    listed = await event_repo_db.search_events(is_active=True)
    assert [row.event.id for row in listed] == [visible.id]
    assert await event_repo_db.count_search_events(is_active=True) == 1


@pytest.mark.parametrize("limit", [True, 0, 102, "100"])
@pytest.mark.asyncio
async def test_user_attended_event_query_rejects_unbounded_limits(
    event_repo_db, limit: Any
) -> None:
    with pytest.raises(ValueError, match="between 1 and 101"):
        await event_repo_db.list_user_attended_events(
            uuid.uuid4(), limit=limit, locale="en"
        )
