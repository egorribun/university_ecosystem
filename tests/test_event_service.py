from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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
    repo.db.rollback = AsyncMock()
    repo.db.add = MagicMock()
    return repo


@pytest.fixture
def mock_vector_service():
    return AsyncMock()


@pytest.fixture
def event_service(mock_repo, mock_vector_service):
    return EventService(repo=mock_repo, vector_service=mock_vector_service)


def create_mock_event(event_id=None):
    mock_event = MagicMock(spec=models.Event)
    mock_event.id = event_id or uuid4()
    mock_event.title = "RU Title"
    mock_event.title_en = "EN Title"
    mock_event.description = "RU Desc"
    mock_event.description_en = "EN Desc"
    mock_event.location = "Loc RU"
    mock_event.location_en = "Loc EN"
    mock_event.event_type = "Type RU"
    mock_event.event_type_en = "Type EN"
    mock_event.starts_at = datetime.now(UTC)
    mock_event.ends_at = datetime.now(UTC) + timedelta(hours=1)
    mock_event.created_by = str(uuid4())
    mock_event.created_at = datetime.now(UTC)
    mock_event.is_active = True
    mock_event.speaker = "Speaker"
    mock_event.image_url = "http://example.com/img.jpg"
    mock_event.about = "About RU"
    mock_event.about_en = "About EN"
    mock_event.files = []
    mock_event.attendance = []
    return mock_event


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
async def test_get_events_issue_token_fails(
    event_service, mock_repo, mock_vector_service
):
    user_id = uuid4()
    mock_event = create_mock_event()
    mock_attendance = MagicMock()
    mock_repo.search_events.return_value = [(mock_event, 10, mock_attendance)]
    mock_repo.count_upcoming.return_value = 1

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=Exception("token_fail"),
    ):
        res = await event_service.get_events(user_id=user_id)
        assert len(res.items) == 1
        assert res.items[0].my_qr_token is None


@pytest.mark.asyncio
async def test_create_event(event_service, mock_repo):
    user_id = uuid4()
    now = datetime.now(UTC)
    event_data = schemas.EventCreate(
        title="Test Event",
        description="Description",
        starts_at=now,
        ends_at=now + timedelta(hours=2),
        location="Location",
        event_type="test_type",
    )

    mock_event = create_mock_event()
    mock_repo.create.return_value = mock_event

    result = await event_service.create_event(event_data, user_id)

    mock_repo.create.assert_awaited_once()
    mock_event.record_event.assert_called_once()
    mock_repo.db.commit.assert_awaited_once()
    mock_repo.db.refresh.assert_awaited_once_with(mock_event)
    assert result == mock_event


@pytest.mark.asyncio
async def test_create_event_invalid_time(event_service):
    user_id = uuid4()
    now = datetime.now(UTC)
    event_data = schemas.EventCreate.model_construct(
        title="Test Event",
        starts_at=now,
        ends_at=now - timedelta(hours=1),
    )
    with pytest.raises(ValueError):
        await event_service.create_event(event_data, user_id)


@pytest.mark.asyncio
async def test_update_event(event_service, mock_repo):
    event_id = uuid4()
    update_data = schemas.EventUpdate(title="Updated Title")

    mock_event = create_mock_event(event_id)
    mock_repo.get.return_value = mock_event

    updated_event = create_mock_event(event_id)
    updated_event.title = "Updated Title"
    mock_repo.update.return_value = updated_event

    result = await event_service.update_event(event_id, update_data)

    mock_repo.get.assert_awaited_once_with(event_id)
    mock_repo.update.assert_awaited_once()
    updated_event.record_event.assert_called_once()
    mock_repo.db.commit.assert_awaited_once()
    mock_repo.db.refresh.assert_awaited_once_with(updated_event)
    assert result == updated_event


@pytest.mark.asyncio
async def test_update_event_invalid_time(event_service, mock_repo):
    event_id = uuid4()
    mock_event = create_mock_event(event_id)
    mock_repo.get.return_value = mock_event

    update_data = schemas.EventUpdate.model_construct(
        starts_at=mock_event.starts_at,
        ends_at=mock_event.starts_at - timedelta(hours=1),
    )
    with pytest.raises(ValueError):
        await event_service.update_event(event_id, update_data)


@pytest.mark.asyncio
async def test_update_event_not_found(event_service, mock_repo):
    mock_repo.get.return_value = None
    update_data = schemas.EventUpdate(title="New")

    from app.core.exceptions.domain import EntityNotFound

    with pytest.raises(EntityNotFound):
        await event_service.update_event(uuid4(), update_data)


@pytest.mark.asyncio
async def test_serialize_event(event_service):
    mock_event = create_mock_event()

    # Test RU locale
    res_ru = event_service.serialize_event(mock_event, locale="ru")
    assert res_ru.title == "RU Title"
    assert res_ru.description == "RU Desc"

    # Test EN locale
    res_en = event_service.serialize_event(mock_event, locale="en")
    assert res_en.title == "EN Title"
    assert res_en.description == "EN Desc"


@pytest.mark.asyncio
async def test_delete_event(event_service, mock_repo):
    event_id = uuid4()
    mock_event = create_mock_event(event_id)
    mock_repo.get.return_value = mock_event

    mock_result = MagicMock()
    mock_result.all.return_value = [("url1",), ("url2",)]
    mock_repo.db.execute.return_value = mock_result

    success = await event_service.delete_event(event_id)
    assert success is True
    mock_repo.delete.assert_awaited_once_with(event_id)
    mock_repo.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_attendance_registration(event_service, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_repo.db.execute.return_value = mock_result

    mock_repo.get.return_value = create_mock_event()

    with (
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="mock_token",
        ),
        patch(
            "app.services.event_service.attendance_tokens.generate_secret",
            return_value="secret",
        ),
        patch(
            "app.services.event_service.attendance_tokens.compute_secret_hmac",
            return_value="hmac",
        ),
    ):
        record = await event_service.register_attendance(data, user_id)
        assert record.user_id == user_id
        assert record.event_id == data.event_id
        mock_repo.db.add.assert_called()
        mock_repo.db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_register_attendance_race_condition(event_service, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None

    mock_attendance = MagicMock(spec=models.EventAttendance)
    mock_attendance.user_id = user_id
    mock_attendance.event_id = data.event_id
    mock_attendance.registered_at = None
    mock_result_found = MagicMock()
    mock_result_found.scalar_one_or_none.return_value = mock_attendance

    mock_repo.db.execute.side_effect = [mock_result_none, mock_result_found]
    mock_repo.db.commit.side_effect = [
        IntegrityError("stmt", "params", "orig"),
        None,
        None,
        None,
    ]

    with (
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="mock_token",
        ),
        patch(
            "app.services.event_service.attendance_tokens.generate_secret",
            return_value="secret",
        ),
        patch(
            "app.services.event_service.attendance_tokens.compute_secret_hmac",
            return_value="hmac",
        ),
        patch(
            "app.services.event_service.attendance_tokens.ensure_secret_material",
            return_value=False,
        ),
    ):
        record = await event_service.register_attendance(data, user_id)
        assert record == mock_attendance
        assert mock_repo.db.rollback.called


@pytest.mark.asyncio
async def test_register_attendance_full_failure(event_service, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_repo.db.execute.return_value = mock_result_none
    mock_repo.db.commit.side_effect = IntegrityError("stmt", "params", "orig")
    mock_repo.get.return_value = None  # Event not found after retry

    with (
        patch(
            "app.services.event_service.attendance_tokens.generate_secret",
            return_value="secret",
        ),
        patch(
            "app.services.event_service.attendance_tokens.compute_secret_hmac",
            return_value="hmac",
        ),
    ):
        from app.core.exceptions.domain import EntityNotFound

        with pytest.raises(EntityNotFound):
            await event_service.register_attendance(data, user_id)


@pytest.mark.asyncio
async def test_unregister_attendance(event_service, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_record = MagicMock(spec=models.EventAttendance)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_record
    mock_repo.db.execute.return_value = mock_result

    res = await event_service.unregister_attendance(data, user_id)
    assert res == {"ok": True}
    mock_repo.db.delete.assert_awaited_once_with(mock_record)
    mock_repo.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_event_detail(event_service, mock_repo):
    event_id = uuid4()
    user_id = uuid4()
    mock_event = create_mock_event(event_id)

    # Correctly mock result from DB execute
    mock_result = MagicMock()
    mock_result.first.return_value = (mock_event, 5, None)
    mock_repo.db.execute.return_value = mock_result

    res = await event_service.get_event_detail(event_id, user_id)
    assert res.id == event_id
    assert res.participant_count == 5
    assert res.is_registered is False


@pytest.mark.asyncio
async def test_get_event_detail_not_found(event_service, mock_repo):
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_repo.db.execute.return_value = mock_result

    res = await event_service.get_event_detail(uuid4(), uuid4())
    assert res is None


@pytest.mark.asyncio
async def test_get_my_events(event_service, mock_repo):
    user_id = uuid4()
    mock_event = create_mock_event()

    mock_attendance = MagicMock(spec=models.EventAttendance)
    mock_attendance.user_id = user_id
    mock_event.attendance = [mock_attendance]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]
    mock_repo.db.execute.return_value = mock_result

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        return_value="mock_token",
    ):
        res = await event_service.get_my_events(user_id, locale="ru")
        assert len(res) == 1
        assert res[0].title == "RU Title"


@pytest.mark.asyncio
async def test_get_event_detail_with_attendance(event_service, mock_repo):
    event_id = uuid4()
    user_id = uuid4()
    mock_event = create_mock_event(event_id)
    mock_attendance = MagicMock(spec=models.EventAttendance)

    mock_result = MagicMock()
    mock_result.first.return_value = (mock_event, 5, mock_attendance)
    mock_repo.db.execute.return_value = mock_result

    with (
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="mock_token",
        ),
        patch(
            "app.services.event_service.attendance_tokens.ensure_secret_material",
            return_value=False,
        ),
    ):
        res = await event_service.get_event_detail(event_id, user_id)
        assert res.id == event_id
        assert res.is_registered is True
        assert res.my_qr_token == "mock_token"


@pytest.mark.asyncio
async def test_unregister_attendance_not_found(event_service, mock_repo):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_repo.db.execute.return_value = mock_result
    res = await event_service.unregister_attendance(MagicMock(), uuid4())
    assert res == {"ok": False}
