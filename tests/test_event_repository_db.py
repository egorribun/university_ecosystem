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


@pytest.mark.parametrize(
    ("time_filter", "expected_titles"),
    [
        (True, {"Upcoming"}),
        (False, {"Archived"}),
        (None, {"Upcoming", "Archived"}),
    ],
)
@pytest.mark.asyncio
async def test_manually_hidden_event_is_excluded_from_listing_and_total(
    event_repo_db, db_session, user_factory, time_filter, expected_titles
):
    """Manual visibility remains mandatory for every temporal filter mode."""
    user = await user_factory()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Event(
                title=title,
                starts_at=now + timedelta(hours=start_offset),
                ends_at=now + timedelta(hours=end_offset),
                created_by=user.id,
                is_active=visible,
                created_at=now,
            )
            for title, start_offset, end_offset, visible in (
                ("Upcoming", 1, 3, True),
                ("Archived", -3, -1, True),
                ("Hidden upcoming", 1, 3, False),
                ("Hidden archived", -3, -1, False),
            )
        ]
    )
    await db_session.flush()

    listed = await event_repo_db.search_events(is_active=time_filter, now=now)
    assert {row.event.title for row in listed} == expected_titles
    count = await event_repo_db.count_search_events(is_active=time_filter, now=now)
    assert count == len(expected_titles)


@pytest.mark.parametrize("limit", [True, 0, 102, "100"])
@pytest.mark.asyncio
async def test_user_attended_event_query_rejects_unbounded_limits(
    event_repo_db, limit: Any
) -> None:
    with pytest.raises(ValueError, match="between 1 and 101"):
        await event_repo_db.list_user_attended_events(
            uuid.uuid4(), limit=limit, locale="en"
        )


@pytest.mark.parametrize(
    ("event_type", "location", "time_filter", "expected_indexes"),
    [
        pytest.param(None, None, None, {0, 1, 2, 3, 4, 6}, id="all-visible"),
        pytest.param(None, None, True, {0, 1, 3, 4, 6}, id="active"),
        pytest.param(None, None, False, {2}, id="archived"),
        pytest.param("WORK", None, None, {0, 1, 2, 4, 6}, id="type"),
        pytest.param(None, "HALL A", None, {0, 1, 2, 3, 6}, id="location"),
        pytest.param("WORK", "HALL A", None, {0, 1, 2, 6}, id="combined"),
        pytest.param("WORK", "HALL A", True, {0, 1, 6}, id="combined-active"),
        pytest.param("WORK", "HALL A", False, {2}, id="combined-archived"),
        pytest.param("missing", None, None, set(), id="no-type-match"),
        pytest.param(None, "missing", None, set(), id="no-location-match"),
    ],
)
@pytest.mark.asyncio
async def test_filtered_event_total_matches_exhaustive_listing(
    event_repo_db,
    db_session,
    user_factory,
    event_type: str | None,
    location: str | None,
    time_filter: bool | None,
    expected_indexes: set[int],
) -> None:
    user = await user_factory()
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    records = [
        Event(
            title=f"Parity {index}",
            event_type=kind,
            location=place,
            event_type_en="workshop" if index == 6 else None,
            location_en="Hall A" if index == 6 else None,
            starts_at=now + timedelta(hours=end_offset - 2),
            ends_at=now + timedelta(hours=end_offset),
            created_at=now,
            created_by=user.id,
            is_active=visible,
        )
        for index, (kind, place, end_offset, visible) in enumerate(
            [
                ("workshop", "Hall A", 2, True),
                ("workshop", "Hall A", 0, True),
                ("workshop", "Hall A", -1, True),
                ("lecture", "Hall A", 2, True),
                ("workshop", "Remote", 2, True),
                ("workshop", "Hall A", 2, False),
                ("Лекция", "Удалённо", 2, True),
            ]
        )
    ]
    db_session.add_all(records)
    await db_session.flush()

    # The limit exceeds this entire isolated fixture, making the list exhaustive.
    listed = await event_repo_db.search_events(
        event_type=event_type,
        location=location,
        is_active=time_filter,
        now=now,
        limit=len(records) + 1,
    )
    expected_ids = {records[index].id for index in expected_indexes}
    listed_ids = [row.event.id for row in listed]
    assert set(listed_ids) == expected_ids
    assert len(listed_ids) == len(expected_ids)

    total = await event_repo_db.count_search_events(
        event_type=event_type,
        location=location,
        is_active=time_filter,
        now=now,
    )
    assert total == len(listed_ids) == len(expected_ids)

    first_page = await event_repo_db.search_events(
        event_type=event_type,
        location=location,
        is_active=time_filter,
        now=now,
        limit=1,
    )
    assert len(first_page) == min(total, 1)
    assert {row.event.id for row in first_page} <= expected_ids
