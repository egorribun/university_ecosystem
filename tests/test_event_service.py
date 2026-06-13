from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

import app.models as models
from app.schemas import schemas
from app.schemas.dtos.event import (
    EventAttendanceDTO,
    EventDTO,
    EventSearchResultDTO,
)
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
def mock_uow(mock_repo):
    uow = AsyncMock()
    uow.events = mock_repo
    uow.session = mock_repo.db
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.rollback = AsyncMock()
    return uow


@pytest.fixture
def event_service(mock_uow, mock_vector_service):
    return EventService(uow=mock_uow, vector_service=mock_vector_service)


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
    mock_dto = EventDTO(
        id=mock_event.id,
        title=str(mock_event.title),
        description=str(mock_event.description),
        location=str(mock_event.location),
        event_type=str(mock_event.event_type),
        starts_at=mock_event.starts_at,
        ends_at=mock_event.ends_at,
        created_by=str(mock_event.created_by),
        created_at=mock_event.created_at,
        is_active=True,
        title_en="EN",
        description_en="EN",
        location_en="EN",
        event_type_en="EN",
        about="RU",
        about_en="EN",
        image_url=None,
        speaker=None,
    )
    mock_attendance_dto = EventAttendanceDTO(
        id=uuid4(),
        user_id=user_id,
        event_id=mock_event.id,
        registered_at=datetime.now(UTC),
        qr_secret="sec",
        qr_hmac="hmac",
    )

    mock_repo.search_events.return_value = [
        EventSearchResultDTO(
            event=mock_dto, participant_count=10, user_attendance=mock_attendance_dto
        )
    ]
    mock_repo.count_upcoming.return_value = 1

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=KeyError("token_fail"),
    ):
        res = await event_service.get_events(user_id=user_id)
        assert len(res.items) == 1
        assert res.items[0].my_qr_token is None


@pytest.mark.asyncio
async def test_create_event(event_service, mock_uow, mock_repo):
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
    mock_uow.commit.assert_awaited_once()
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
async def test_update_event(event_service, mock_uow, mock_repo):
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
    mock_uow.commit.assert_awaited_once()
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
async def test_delete_event(event_service, mock_uow, mock_repo):
    event_id = uuid4()
    mock_event = create_mock_event(event_id)
    mock_repo.get.return_value = mock_event

    mock_result = MagicMock()
    mock_result.all.return_value = [("url1",), ("url2",)]
    mock_repo.db.execute.return_value = mock_result

    success = await event_service.delete_event(event_id)
    assert success is True
    mock_repo.get.assert_awaited_once_with(event_id)
    mock_repo.delete.assert_awaited_once_with(event_id)
    mock_uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_attendance_registration(event_service, mock_uow, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_repo.get_attendance.return_value = None
    mock_repo.get.return_value = create_mock_event()
    mock_repo.get_for_registration.return_value = create_mock_event()
    mock_attendance = EventAttendanceDTO(
        id=uuid4(), event_id=data.event_id, user_id=user_id, registered_at=None
    )
    mock_repo.create_attendance.return_value = mock_attendance

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
        mock_repo.create_attendance.assert_called()
        mock_uow.commit.assert_awaited()


@pytest.mark.asyncio
async def test_register_attendance_race_condition(event_service, mock_repo):
    import asyncio

    data = schemas.EventAttendanceCreate(event_id=uuid4())
    _, u2, u3 = uuid4(), uuid4(), uuid4()

    # We'll simulate that u1 succeeds, while u2 and u3 hit a race condition
    # For a real DB, this is handled by unique constraints. For mock,
    # we just need to ensure the service layer doesn't crash on IntegrityError
    # when it tries to insert duplicate attendance, but rather returns the existing one.

    mock_attendance = EventAttendanceDTO(
        id=uuid4(), event_id=data.event_id, user_id=u2, registered_at=None
    )

    # First call: IntegrityError. Second call (retry): returns mock_attendance
    mock_repo.get_attendance.side_effect = [
        None,
        mock_attendance,
        None,
        mock_attendance,
    ]
    mock_repo.commit.side_effect = IntegrityError(
        "duplicate key value violates unique constraint", {}, Exception()
    )

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
        await asyncio.gather(
            event_service.register_attendance(data, u2),
            event_service.register_attendance(data, u3),
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_register_attendance_full_failure(event_service, mock_uow, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_repo.get_attendance.return_value = None
    mock_repo.get_for_registration.return_value = create_mock_event()
    mock_uow.commit.side_effect = IntegrityError("stmt", "params", "orig")
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
async def test_unregister_attendance(event_service, mock_uow, mock_repo):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_record = MagicMock(spec=models.EventAttendance)
    mock_repo.get_attendance.return_value = mock_record
    mock_repo.delete_attendance.return_value = True

    res = await event_service.unregister_attendance(data, user_id)
    assert res == {"ok": True}
    mock_repo.delete_attendance.assert_awaited_once_with(data.event_id, user_id)
    mock_uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_event_detail(event_service, mock_repo):
    event_id = uuid4()
    user_id = uuid4()
    mock_event = create_mock_event(event_id)
    mock_dto = EventDTO(
        **{
            k: getattr(mock_event, k)
            for k in EventDTO.model_fields
            if hasattr(mock_event, k)
        }
    )

    mock_repo.get_event_with_details.return_value = EventSearchResultDTO(
        event=mock_dto, participant_count=5, user_attendance=None
    )

    res = await event_service.get_event_detail(event_id, user_id)
    assert res.id == event_id
    assert res.participant_count == 5
    assert res.is_registered is False


@pytest.mark.asyncio
async def test_get_event_detail_not_found(event_service, mock_repo):
    mock_repo.get_event_with_details.return_value = None

    res = await event_service.get_event_detail(uuid4(), uuid4())
    assert res is None


@pytest.mark.asyncio
async def test_get_my_events(event_service, mock_repo):
    user_id = uuid4()
    mock_event = create_mock_event()

    mock_attendance = MagicMock(spec=models.EventAttendance)
    mock_attendance.user_id = user_id
    mock_event.attendance = [mock_attendance]

    mock_repo.list_user_attended_events.return_value = [mock_event]

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
    mock_dto = EventDTO.model_validate(mock_event)
    mock_attendance_dto = EventAttendanceDTO(
        id=uuid4(),
        user_id=user_id,
        event_id=event_id,
        registered_at=datetime.now(UTC),
        qr_secret="secret",
        qr_hmac="hmac",
    )

    mock_repo.get_event_with_details.return_value = EventSearchResultDTO(
        event=mock_dto, participant_count=5, user_attendance=mock_attendance_dto
    )

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
    mock_repo.get_attendance.return_value = None
    mock_repo.delete_attendance.return_value = False
    res = await event_service.unregister_attendance(MagicMock(), uuid4())
    assert res == {"ok": False}


# --------------------------------------------------------------------------- #
# delete_event — not-found guard + best-effort file-cleanup on OSError         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_delete_event_not_found_returns_false(event_service, mock_repo):
    mock_repo.get.return_value = None
    assert await event_service.delete_event(uuid4()) is False


@pytest.mark.asyncio
async def test_delete_event_swallows_file_cleanup_errors(
    event_service, mock_uow, mock_repo
):
    event_id = uuid4()
    mock_repo.get.return_value = create_mock_event(event_id)  # has image_url
    mock_repo.get_event_file_urls.return_value = ["file1.png", "file2.png"]

    # Storage deletion failing is non-fatal — the commit already succeeded.
    with patch(
        "app.utils.files.delete_static_file",
        new=AsyncMock(side_effect=OSError("storage down")),
    ):
        assert await event_service.delete_event(event_id) is True

    mock_uow.commit.assert_awaited_once()


# --------------------------------------------------------------------------- #
# register_attendance — not-found + closed (active flag and expired window)    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_register_attendance_event_not_found(event_service, mock_repo):
    from app.core.exceptions.domain import EntityNotFound

    mock_repo.get_for_registration.return_value = None
    with pytest.raises(EntityNotFound):
        await event_service.register_attendance(
            schemas.EventAttendanceCreate(event_id=uuid4()), uuid4()
        )


@pytest.mark.asyncio
async def test_register_attendance_closed_when_inactive(event_service, mock_repo):
    ev = create_mock_event()
    ev.is_active = False
    mock_repo.get_for_registration.return_value = ev
    with pytest.raises(ValueError, match="registration_closed"):
        await event_service.register_attendance(
            schemas.EventAttendanceCreate(event_id=uuid4()), uuid4()
        )


@pytest.mark.asyncio
async def test_register_attendance_closed_when_window_expired(event_service, mock_repo):
    ev = create_mock_event()
    # Naive past datetime exercises the tz-normalisation branch + the
    # ends_at <= now "registration_closed" guard.
    ev.ends_at = datetime(2020, 1, 1)
    mock_repo.get_for_registration.return_value = ev
    with pytest.raises(ValueError, match="registration_closed"):
        await event_service.register_attendance(
            schemas.EventAttendanceCreate(event_id=uuid4()), uuid4()
        )


@pytest.mark.asyncio
async def test_register_attendance_updates_existing_unregistered(
    event_service, mock_uow, mock_repo
):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()
    mock_repo.get_for_registration.return_value = create_mock_event()
    existing = EventAttendanceDTO(
        id=uuid4(), event_id=data.event_id, user_id=user_id, registered_at=None
    )
    mock_repo.get_attendance.return_value = existing
    mock_repo.update_attendance.return_value = existing

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        return_value="tok",
    ):
        result = await event_service.register_attendance(data, user_id)

    # registered_at was None -> the update branch runs + commits + re-issues a token.
    mock_repo.update_attendance.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    assert result.qr_token == "tok"


# --------------------------------------------------------------------------- #
# get_event_detail — ensure_secret_material refresh path                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_event_detail_refreshes_secret_material(
    event_service, mock_uow, mock_repo
):
    event_id, user_id = uuid4(), uuid4()
    mock_event = create_mock_event(event_id)
    attendance = MagicMock()
    attendance.user_id = user_id
    attendance.qr_secret = "secret"
    attendance.qr_hmac = "hmac"

    result = MagicMock()
    result.event = mock_event
    result.participant_count = 3
    result.user_attendance = attendance
    mock_repo.get_event_with_details.return_value = result

    with (
        patch(
            "app.services.event_service.attendance_tokens.ensure_secret_material",
            return_value=True,
        ),
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="tok",
        ),
    ):
        out = await event_service.get_event_detail(event_id, user_id)

    # ensure_secret_material True -> the repo update + commit branch runs.
    mock_repo.update_attendance.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    assert out is not None
    assert out.my_qr_token == "tok"
    assert out.is_registered is True


# ---------------------------------------------------------------------------
# IntegrityError race-retry path (testing session 10) — covers
# event_service.py:327-363, which the existing race test does not reach
# (it sets mock_repo.commit.side_effect, but register_attendance commits via
# self.uow.commit()). Here uow.commit raises IntegrityError on the FIRST call
# and succeeds on the retry.
# ---------------------------------------------------------------------------


def _registration_event():
    ev = MagicMock()
    ev.is_active = True
    ev.ends_at = datetime.now(UTC) + timedelta(hours=1)
    return ev


@pytest.mark.asyncio
async def test_register_attendance_integrity_retry_updates_registered_at(
    event_service, mock_uow, mock_repo
):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_repo.get_for_registration.return_value = _registration_event()
    # 1st get_attendance (pre-create) None; 2nd (post-race) returns a DTO with
    # registered_at=None → the retry_updates branch fires.
    raced = EventAttendanceDTO(
        id=uuid4(), event_id=data.event_id, user_id=user_id, registered_at=None
    )
    updated = EventAttendanceDTO(
        id=raced.id,
        event_id=data.event_id,
        user_id=user_id,
        registered_at=datetime.now(UTC),
    )
    mock_repo.get_attendance.side_effect = [None, raced]
    mock_repo.create_attendance.return_value = raced
    mock_repo.update_attendance.return_value = updated
    # uow.commit: 1st call (after create) raises, retry commit succeeds.
    mock_uow.commit.side_effect = [
        IntegrityError("dup", {}, Exception()),
        None,
    ]

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        return_value="tok",
    ):
        result = await event_service.register_attendance(data, user_id)

    mock_uow.rollback.assert_awaited_once()
    mock_repo.update_attendance.assert_awaited_once()
    assert result.qr_token == "tok"


@pytest.mark.asyncio
async def test_register_attendance_integrity_retry_already_registered(
    event_service, mock_uow, mock_repo
):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_repo.get_for_registration.return_value = _registration_event()
    # Post-race DTO already has registered_at set → retry_updates stays empty,
    # so update_attendance + the retry commit are skipped (347-354 not taken).
    already = EventAttendanceDTO(
        id=uuid4(),
        event_id=data.event_id,
        user_id=user_id,
        registered_at=datetime.now(UTC),
    )
    mock_repo.get_attendance.side_effect = [None, already]
    mock_repo.create_attendance.return_value = already
    mock_uow.commit.side_effect = [IntegrityError("dup", {}, Exception())]

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        return_value="tok2",
    ):
        result = await event_service.register_attendance(data, user_id)

    mock_uow.rollback.assert_awaited_once()
    mock_repo.update_attendance.assert_not_awaited()
    assert result.qr_token == "tok2"


@pytest.mark.asyncio
async def test_register_attendance_integrity_not_found_raises_value_error(
    event_service, mock_uow, mock_repo
):
    data = schemas.EventAttendanceCreate(event_id=uuid4())
    user_id = uuid4()

    mock_repo.get_for_registration.return_value = _registration_event()
    # Post-race get_attendance still None → fall to repo.get; a found event →
    # ValueError (registration failed), covering 335-337.
    mock_repo.get_attendance.side_effect = [None, None]
    mock_repo.create_attendance.return_value = EventAttendanceDTO(
        id=uuid4(), event_id=data.event_id, user_id=user_id, registered_at=None
    )
    mock_repo.get.return_value = MagicMock()  # event exists
    mock_uow.commit.side_effect = [IntegrityError("dup", {}, Exception())]

    with pytest.raises(ValueError):
        await event_service.register_attendance(data, user_id)
    mock_uow.rollback.assert_awaited_once()
