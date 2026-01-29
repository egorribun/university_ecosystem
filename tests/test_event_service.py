from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import models
from app.schemas import schemas
from app.services.event_service import EventService


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    # Mock db attribute for commit/refresh
    repo.db = AsyncMock()
    repo.db.commit = AsyncMock()
    repo.db.refresh = AsyncMock()
    return repo


@pytest.fixture
def mock_vector_service():
    return AsyncMock()


@pytest.fixture
def event_service(mock_repo, mock_vector_service):
    return EventService(repo=mock_repo, vector_service=mock_vector_service)


@pytest.mark.asyncio
async def test_get_events(event_service, mock_repo, mock_vector_service):
    mock_vector_service.get_embedding.return_value = [0.1, 0.2, 0.3]
    mock_repo.search_events.return_value = []

    await event_service.get_events(search="test")

    mock_vector_service.get_embedding.assert_awaited_once_with("test")
    mock_repo.search_events.assert_awaited_once()
    kwargs = mock_repo.search_events.call_args.kwargs
    assert kwargs["search_query"] == "test"
    assert kwargs["query_embedding"] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_create_event(event_service, mock_repo):
    user_id = 1
    # Use valid schema fields: starts_at, ends_at, event_type
    now = datetime.now(UTC)
    event_data = schemas.EventCreate(
        title="Test Event",
        description="Description",
        starts_at=now,
        ends_at=now + timedelta(hours=2),
        location="Location",
        event_type="test_type",
    )

    mock_event = MagicMock(spec=models.Event)
    mock_event.id = 100
    mock_event.title = "Test Event"
    mock_repo.create.return_value = mock_event

    result = await event_service.create_event(event_data, user_id)

    mock_repo.create.assert_awaited_once()
    # Check that record_event was called
    mock_event.record_event.assert_called_once()
    mock_repo.db.commit.assert_awaited_once()
    mock_repo.db.refresh.assert_awaited_once_with(mock_event)
    assert result == mock_event


@pytest.mark.asyncio
async def test_update_event(event_service, mock_repo):
    event_id = 100
    update_data = schemas.EventUpdate(title="Updated Title")

    mock_event = MagicMock(spec=models.Event)
    mock_event.id = event_id
    mock_event.title = "Old Title"
    mock_repo.get.return_value = mock_event

    updated_event = MagicMock(spec=models.Event)
    updated_event.id = event_id
    updated_event.title = "Updated Title"
    mock_repo.update.return_value = updated_event

    result = await event_service.update_event(event_id, update_data)

    mock_repo.get.assert_awaited_once_with(event_id)
    mock_repo.update.assert_awaited_once()
    # Should be called because title changed
    updated_event.record_event.assert_called_once()
    mock_repo.db.commit.assert_awaited_once()
    mock_repo.db.refresh.assert_awaited_once_with(updated_event)
    assert result == updated_event


@pytest.mark.asyncio
async def test_update_event_not_found(event_service, mock_repo):
    mock_repo.get.return_value = None
    update_data = schemas.EventUpdate(title="New")

    from app.core.exceptions.domain import EntityNotFound

    with pytest.raises(EntityNotFound):
        await event_service.update_event(999, update_data)
