import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.repositories.event_repository import EventRepository


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def repo(mock_db):
    return EventRepository(mock_db)


@pytest.mark.asyncio
async def test_get_with_details(repo, mock_db):
    event_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = Event(
        id=event_id,
        title="Test Event",
        title_en="Test Event EN",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        created_by=uuid.uuid4(),
        is_active=True,
    )
    mock_db.execute.return_value = mock_result

    event = await repo.get_with_details(event_id)
    assert event.id == event_id
    assert event.title == "Test Event"


@pytest.mark.asyncio
async def test_get_upcoming(repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        Event(
            id=uuid.uuid4(),
            title="Upcoming",
            title_en="Upcoming EN",
            starts_at=datetime.now(UTC),
            ends_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            created_by=uuid.uuid4(),
            is_active=True,
        )
    ]
    mock_db.execute.return_value = mock_result

    events = await repo.get_upcoming()
    assert len(events) == 1
    assert events[0].title == "Upcoming"


@pytest.mark.asyncio
async def test_search_events_basic(repo, mock_db):
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    results = await repo.search_events(search_query="test")
    assert results == []


@pytest.mark.asyncio
async def test_count_upcoming(repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    mock_db.execute.return_value = mock_result

    count = await repo.count_upcoming()
    assert count == 5


@pytest.mark.asyncio
async def test_get_by_organizer(repo, mock_db):
    org_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    results = await repo.get_by_organizer(org_id)
    assert results == []
