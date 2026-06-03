import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

import app.models as models
from app.api.events import all_events, attend, create_event, upload_event_file
from app.schemas import schemas


@pytest.fixture
def mock_user():
    user = MagicMock(spec=models.User)
    user.id = uuid.uuid4()
    user.role = "admin"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.app.state.cache = MagicMock()
    return request


@pytest.mark.asyncio
async def test_create_event_success(mock_user, mock_db, mock_request):
    data = schemas.EventCreate(
        title="Test Event",
        description="Test Desc",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
        location="Test Loc",
        event_type="meeting",
    )

    mock_events = MagicMock()
    # Explicitly set create_event as AsyncMock since it's awaited in the router
    mock_events.create_event = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    # serialize_event is synchronous
    mock_events.serialize_event.return_value = {"id": "test"}

    mock_notifications = AsyncMock()

    with patch("app.api.events.resolve_locale", return_value="en"):
        result = await create_event(
            data=data,
            request=mock_request,
            background=MagicMock(),
            user=mock_user,
            notifications=mock_notifications,
            events=mock_events,
        )

    assert result == {"id": "test"}
    mock_events.create_event.assert_called_once()


@pytest.mark.asyncio
async def test_all_events_success(mock_user, mock_db, mock_request):
    mock_events = AsyncMock()
    mock_events.get_events.return_value = {"items": [], "total": 0}

    with patch("app.api.events.resolve_locale", return_value="en"):
        result = await all_events(
            request=mock_request,
            response=MagicMock(),
            user=mock_user,
            search="test",
            type="meeting",
            location="loc",
            is_active=True,
            limit=20,
            cursor=None,
            if_none_match=None,
            events=mock_events,
        )

    assert result == {"items": [], "total": 0}
    mock_events.get_events.assert_called_once()


@pytest.mark.asyncio
async def test_attend_success(mock_user, mock_db, mock_request):
    mock_user.role = "student"
    event_id = uuid.uuid4()
    data = schemas.EventAttendanceCreate(event_id=event_id)

    mock_event = MagicMock()
    mock_event.is_active = True
    mock_event.ends_at = datetime.now(UTC) + timedelta(days=1)
    mock_db.get.return_value = mock_event

    mock_events = AsyncMock()
    # Mocking DTO object for pydantic validation
    mock_dto = MagicMock()
    mock_dto.id = uuid.uuid4()
    mock_dto.user_id = mock_user.id
    mock_dto.event_id = event_id
    mock_dto.registered_at = datetime.now(UTC)
    mock_dto.qr_token = "token_value"

    mock_events.register_attendance.return_value = mock_dto

    with patch("app.api.events.resolve_locale", return_value="en"):
        result = await attend(
            data=data,
            request=mock_request,
            db=mock_db,
            user=mock_user,
            events=mock_events,
        )

    assert result is not None
    mock_events.register_attendance.assert_called_once()


@pytest.mark.asyncio
async def test_upload_event_file_success(mock_user, mock_db, mock_request):
    event_id = uuid.uuid4()
    mock_file = MagicMock()
    mock_file.size = 100

    mock_event = MagicMock(id=event_id)
    mock_db.get.return_value = mock_event

    mock_checker = AsyncMock()
    mock_checker.check_permission.return_value = True

    with (
        patch("app.api.events.resolve_locale", return_value="en"),
        patch("app.api.events.scan_for_malware", return_value=None),
        patch("app.api.events.save_attachment", return_value="http://file"),
    ):
        result = await upload_event_file(
            event_id=event_id,
            file=mock_file,
            request=mock_request,
            db=mock_db,
            user=mock_user,
            checker=mock_checker,
        )

    assert result.file_url == "http://file"
    mock_db.commit.assert_called_once()
