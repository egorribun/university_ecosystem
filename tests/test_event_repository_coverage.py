import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Event, EventFile
from app.repositories.event_repository import EventRepository, get_event_repository
from app.utils.uuid_v7 import generate_uuid7


@pytest.fixture
def clean_events(db_session):
    pass


def test_event_repository_factory_and_properties(db_session):
    repo = get_event_repository(db_session)
    assert repo.model == Event
    assert repo.db == db_session


@pytest.mark.asyncio
async def test_event_repository_attendance(db_session, user_factory):
    user = await user_factory()
    repo = EventRepository(db_session)

    starts = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    ends = starts + datetime.timedelta(hours=2)

    event = Event(
        id=generate_uuid7(),
        title="Workshop",
        starts_at=starts,
        ends_at=ends,
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()

    # 1. Create attendance
    attendance = await repo.create_attendance(
        id=generate_uuid7(),
        event_id=event.id,
        user_id=user.id,
        qr_secret="sec",  # pragma: allowlist secret
        qr_hmac="hmac",
    )
    assert attendance.event_id == event.id

    # 2. Get attendance
    loaded = await repo.get_attendance(event.id, user.id)
    assert loaded is not None
    assert loaded.qr_secret == "sec"  # pragma: allowlist secret

    # 3. Update attendance
    updated = await repo.update_attendance(
        event.id,
        user.id,
        {"qr_secret": "updated_sec"},  # pragma: allowlist secret
    )
    assert updated is not None
    assert updated.qr_secret == "updated_sec"  # pragma: allowlist secret

    # Update non-existent (passing actual fields, empty updates is a syntax error in SQLite)
    assert (
        await repo.update_attendance(uuid.uuid4(), user.id, {"qr_secret": "no"})
        is None  # pragma: allowlist secret
    )

    # 4. List user attended events
    events = await repo.list_user_attended_events(user.id)
    assert len(events) == 1
    assert events[0].id == event.id

    # 5. Delete attendance
    deleted = await repo.delete_attendance(event.id, user.id)
    assert deleted is True

    # Delete non-existent
    deleted_missing = await repo.delete_attendance(event.id, user.id)
    assert deleted_missing is False


@pytest.mark.asyncio
async def test_event_repository_files_and_analytics(db_session, user_factory):
    user = await user_factory()
    repo = EventRepository(db_session)

    starts = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    ends = starts + datetime.timedelta(hours=2)

    event = Event(
        id=generate_uuid7(),
        title="Event with Files",
        starts_at=starts,
        ends_at=ends,
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()

    file_rec = EventFile(
        id=generate_uuid7(),
        event_id=event.id,
        file_url="https://example.com/file.pdf",
    )
    db_session.add(file_rec)
    await db_session.commit()

    # 1. Get file URLs
    urls = await repo.get_event_file_urls(event.id)
    assert urls == ["https://example.com/file.pdf"]

    # 2. Delete event files
    await repo.delete_event_files(event.id)
    urls_after = await repo.get_event_file_urls(event.id)
    assert urls_after == []

    # 3. Mock database execute for get_analytics_data (since e.max_attendees column does not exist on SQLite model schema)
    mock_execute = AsyncMock()
    mock_analytics_result = MagicMock()
    mock_analytics_result.fetchall.return_value = [
        (event.id, "Event with Files", starts, "Location", 0, 100)
    ]
    mock_analytics_result.keys.return_value = [
        "id",
        "title",
        "start_time",
        "location",
        "attendees_count",
        "max_attendees",
    ]
    mock_execute.return_value = mock_analytics_result

    original_execute = db_session.execute
    db_session.execute = mock_execute
    try:
        data, keys = await repo.get_analytics_data()
        assert len(data) == 1
        assert "attendees_count" in keys

        # Get analytics data with start_date filter
        data_filtered, _ = await repo.get_analytics_data(start_date=starts)
        assert len(data_filtered) == 1
    finally:
        db_session.execute = original_execute


@pytest.mark.asyncio
async def test_event_repository_search_events_sqlite_compatible(
    db_session, user_factory
):
    user = await user_factory()
    repo = EventRepository(db_session)

    starts = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    ends = starts + datetime.timedelta(hours=2)

    event = Event(
        id=generate_uuid7(),
        title="SQLite Compatible Search",
        event_type="webinar",
        location="Remote",
        starts_at=starts,
        ends_at=ends,
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()

    # 1. Test get_event_with_details (without attendance)
    det = await repo.get_event_with_details(event.id, user.id)
    assert det is not None
    assert det.event.title == "SQLite Compatible Search"
    assert det.participant_count == 0
    assert det.user_attendance is None

    # Test get_event_with_details with user_id = None
    det_no_user = await repo.get_event_with_details(event.id, None)
    assert det_no_user is not None
    assert det_no_user.user_attendance is None

    # Test get_event_with_details for missing event
    assert await repo.get_event_with_details(uuid.uuid4(), user.id) is None

    # 2. Test search_events with empty search query (compatible with SQLite)
    results = await repo.search_events(
        user_id=user.id,
        event_type="webinar",
        location="Remote",
        is_active=True,
        limit=5,
    )
    assert len(results) >= 1
    assert results[0].event.id == event.id

    # Call with is_active=False
    results_inactive = await repo.search_events(
        is_active=False,
        limit=5,
    )
    assert len(results_inactive) == 0

    # Call with cursor
    results_cursor = await repo.search_events(
        cursor=(starts, event.id),
        limit=5,
    )
    assert len(results_cursor) == 0

    # Call with no conditions (is_active=None, location=None, event_type=None)
    results_all = await repo.search_events(
        is_active=None,
        limit=5,
    )
    assert len(results_all) >= 1


@pytest.mark.asyncio
async def test_event_repository_search_events_postgres_query_builder(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "semantic_search_enabled", True)

    # Mock AsyncDatabaseSession to verify generated SQL statement without running on SQLite
    mock_db = AsyncMock()
    mock_result = MagicMock()
    # Mocking result.all() to return a mock row with a real EventDTO
    from app.schemas.dtos import EventDTO

    mock_event_dto = EventDTO(
        id=uuid.uuid4(),
        title="Rust Conf",
        title_en="Rust Conf EN",
        description="Description",
        description_en="Description EN",
        location="Remote",
        location_en="Remote EN",
        event_type="conference",
        event_type_en="conf",
        starts_at=datetime.datetime.now(datetime.UTC),
        ends_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        created_by=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.UTC),
        is_active=True,
        speaker=None,
        image_url=None,
        about=None,
        about_en=None,
    )
    mock_row = (mock_event_dto, 1, None, 0.5)
    mock_result.all.return_value = [mock_row]
    mock_db.execute.return_value = mock_result

    repo = EventRepository(mock_db)

    # 1. Run search_events with search_query and mock embedding
    await repo.search_events(
        search_query="rust conference",
        query_embedding=[0.1] * 1536,
    )

    # Verify mock execute was called and inspect the compiled SQL
    assert mock_db.execute.called
    stmt = mock_db.execute.call_args[0][0]
    sql_str = str(stmt)

    # Assert PostgreSQL-specific tsquery and @@ operations exist in compiled query
    assert "@@" in sql_str
    assert "plainto_tsquery" in sql_str
    assert "<=>" in sql_str

    # 2. Run search_events with search_query but NO embedding to test the False branch
    await repo.search_events(
        search_query="rust conference",
        query_embedding=None,
    )


@pytest.mark.asyncio
async def test_title_search_keyset_preserves_ties_without_repeating_events(
    db_session, user_factory
):
    user = await user_factory()
    starts = datetime.datetime(2026, 10, 1, 12, tzinfo=datetime.UTC)
    expected = [uuid.UUID(int=value) for value in (40, 30, 20, 10, 50)]
    offsets = [1, 0, 0, 0, -1]
    events = [
        Event(
            id=event_id,
            title="Keyset Workshop",
            starts_at=starts + datetime.timedelta(days=offset),
            ends_at=starts + datetime.timedelta(days=offset, hours=1),
            created_by=user.id,
        )
        for event_id, offset in zip(expected, offsets, strict=True)
    ]
    db_session.add_all(events)
    db_session.add(
        Event(
            title="Unrelated event",
            starts_at=starts,
            ends_at=starts + datetime.timedelta(hours=1),
            created_by=user.id,
        )
    )
    await db_session.commit()
    repo = EventRepository(db_session)

    first = await repo.search("  KEYSET  ", limit=2)
    second = await repo.search(
        "keyset",
        limit=2,
        after_starts_at=first[-1].starts_at,
        after_id=first[-1].id,
    )
    third = await repo.search(
        "keyset",
        limit=2,
        after_starts_at=second[-1].starts_at,
        after_id=second[-1].id,
    )
    assert [event.id for event in first] == expected[:2]
    assert [event.id for event in second] == expected[2:4]
    assert [event.id for event in third] == expected[4:]
    assert (
        await repo.search(
            "keyset",
            limit=2,
            after_starts_at=third[-1].starts_at,
            after_id=third[-1].id,
        )
        == []
    )
