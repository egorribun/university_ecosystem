"""Closure tests for event service pagination, cleanup, and race paths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.schemas import schemas
from app.schemas.dtos.event import (
    EventAttendanceDTO,
    EventDTO,
    EventFileDTO,
    EventSearchResultDTO,
)
from app.services.event_service import EventService


def _event(event_id=None, *, image_url=None) -> EventDTO:
    now = datetime.now(UTC)
    return EventDTO(
        id=event_id or uuid4(),
        title="Russian title",
        title_en="English title",
        description="Description",
        description_en="Description EN",
        location="Room",
        location_en="Room EN",
        event_type="Lecture",
        event_type_en="Lecture EN",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=uuid4(),
        created_at=now,
        is_active=True,
        speaker="Speaker",
        image_url=image_url,
        about="About",
        about_en="About EN",
    )


@pytest.fixture
def event_service_closure():
    repo = AsyncMock()
    uow = MagicMock()
    uow.events = repo
    uow.session = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    return EventService(uow, AsyncMock()), uow, repo


@pytest.mark.asyncio
async def test_get_event_by_id_delegates_to_repository(event_service_closure):
    service, _, repo = event_service_closure
    expected = _event()
    repo.get.return_value = expected

    assert await service.get_event_by_id(expected.id) is expected
    repo.get.assert_awaited_once_with(expected.id)


def test_serialize_event_validates_raw_file_dto(event_service_closure):
    service, _, _ = event_service_closure
    event = _event()
    file_dto = EventFileDTO(
        id=uuid4(), event_id=event.id, file_url="/files/agenda.pdf", description=None
    )
    existing_file = schemas.EventFileOut.model_validate(file_dto)

    output = service.serialize_event(
        event, "en", files=[existing_file, file_dto.model_dump()]
    )

    assert [item.file_url for item in output.files] == [
        "/files/agenda.pdf",
        "/files/agenda.pdf",
    ]


@pytest.mark.asyncio
async def test_get_events_cursor_page_builds_next_cursor_without_total(
    event_service_closure,
):
    service, _, repo = event_service_closure
    repo.search_events.return_value = [
        EventSearchResultDTO(event=_event(), participant_count=2, user_attendance=None),
        EventSearchResultDTO(event=_event(), participant_count=3, user_attendance=None),
    ]

    result = await service.get_events(cursor="opaque", limit=1, locale="en")

    assert result.total is None
    assert result.has_more is True
    assert result.next_cursor is not None
    repo.count_upcoming.assert_not_awaited()
    repo.count.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_events_non_active_first_page_uses_total_count(event_service_closure):
    service, _, repo = event_service_closure
    repo.search_events.return_value = []
    repo.count.return_value = 4

    result = await service.get_events(is_active=False, locale="en")

    assert result.total == 4
    repo.count.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_event_accepts_valid_time_window(event_service_closure):
    service, uow, repo = event_service_closure
    event = _event()
    updated = _event(event.id)
    repo.get.return_value = event
    repo.update.return_value = updated
    data = schemas.EventUpdate.model_construct(
        starts_at=event.starts_at + timedelta(minutes=5),
        ends_at=event.ends_at + timedelta(minutes=5),
    )

    assert await service.update_event(event.id, data) is updated
    uow.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_delete_event_skips_image_cleanup_when_image_is_missing(
    event_service_closure,
):
    service, _, repo = event_service_closure
    event = _event(image_url=None)
    repo.get.return_value = event
    repo.get_event_file_urls.return_value = []

    with patch("app.utils.files.delete_static_file", new=AsyncMock()) as delete_file:
        assert await service.delete_event(event.id) is True

    delete_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_attendance_existing_record_does_not_update(
    event_service_closure,
):
    service, uow, repo = event_service_closure
    event = _event()
    user_id = uuid4()
    attendance = EventAttendanceDTO(
        id=uuid4(), event_id=event.id, user_id=user_id, registered_at=datetime.now(UTC)
    )
    repo.get_for_registration.return_value = event
    repo.get_attendance.return_value = attendance

    with patch(
        "app.services.event_service.attendance_tokens.issue_token", return_value="tok"
    ):
        result = await service.register_attendance(
            schemas.EventAttendanceCreate(event_id=event.id), user_id
        )

    assert result.qr_token == "tok"
    repo.update_attendance.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_attendance_race_retry_keeps_existing_when_update_returns_none(
    event_service_closure,
):
    service, uow, repo = event_service_closure
    event = _event()
    user_id = uuid4()
    raced = EventAttendanceDTO(
        id=uuid4(), event_id=event.id, user_id=user_id, registered_at=None
    )
    repo.get_for_registration.return_value = event
    repo.get_attendance.side_effect = [None, raced]
    repo.create_attendance.return_value = raced
    repo.update_attendance.return_value = None
    uow.commit.side_effect = [IntegrityError("duplicate", {}, Exception()), None]

    with (
        patch(
            "app.services.event_service.attendance_tokens.generate_secret",
            return_value="secret",
        ),
        patch(
            "app.services.event_service.attendance_tokens.compute_secret_hmac",
            return_value="hmac",
        ),
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="tok",
        ),
        patch(
            "app.services.event_service.stats_cache.invalidate_user_stats_cache",
            new=AsyncMock(),
        ),
    ):
        result = await service.register_attendance(
            schemas.EventAttendanceCreate(event_id=event.id), user_id
        )

    assert result.qr_token == "tok"
    repo.update_attendance.assert_awaited_once()
    uow.rollback.assert_awaited_once_with()
