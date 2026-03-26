import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, UploadFile

import app.models as models
from app.api.events import (
    attend,
    create_event,
    delete_event_file,
    semantic_search,
    upload_event_file,
    upload_event_image,
)
from app.schemas import schemas


@pytest.fixture
def request_mock():
    req = MagicMock(spec=Request)
    req.app.state.cache = MagicMock()
    return req


@pytest.mark.asyncio
async def test_create_event_value_error(request_mock):
    events_service = MagicMock()
    events_service.create_event = AsyncMock(side_effect=ValueError("Invalid data"))

    user = MagicMock(spec=models.User)
    user.role = "teacher"

    data = schemas.EventCreate(
        title="Test",
        description="Desc",
        location="Loc",
        event_type="Lecture",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
    )

    with patch("app.api.events.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await create_event(
                data, request_mock, MagicMock(), user, MagicMock(), events_service
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_attend_forbidden_for_teacher(request_mock):
    user = MagicMock(spec=models.User)
    user.role = "teacher"

    with patch("app.api.events.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await attend(MagicMock(), request_mock, MagicMock(), user, MagicMock())
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_attend_registration_closed(request_mock):
    user = MagicMock(spec=models.User)
    user.role = "student"

    event = MagicMock(spec=models.Event)
    event.is_active = True
    event.ends_at = datetime.now(UTC) - timedelta(minutes=1)

    db = AsyncMock()
    db.get.return_value = event

    with patch("app.api.events.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await attend(MagicMock(), request_mock, db, user, MagicMock())
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_upload_event_file_forbidden(request_mock):
    db = AsyncMock()
    db.get.return_value = MagicMock(spec=models.Event)

    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=False)

    with patch("app.api.events.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await upload_event_file(
                uuid.uuid4(),
                MagicMock(),
                request=request_mock,
                db=db,
                user=MagicMock(),
                checker=checker,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_event_image_exception(request_mock):
    db = AsyncMock()
    db.get.return_value = MagicMock(spec=models.Event)

    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)

    file = MagicMock(spec=UploadFile)
    file.size = 100

    with patch("app.api.events.resolve_locale", return_value="en"):
        with patch("app.api.events.scan_for_malware", AsyncMock()):
            with patch(
                "app.api.events.save_upload",
                AsyncMock(side_effect=Exception("Save failed")),
            ):
                with patch("app.api.events.delete_static_file", AsyncMock()):
                    with pytest.raises(Exception):  # noqa: B017
                        await upload_event_image(
                            file,
                            request=request_mock,
                            user=MagicMock(),
                            event_id=uuid.uuid4(),
                            db=db,
                            checker=checker,
                        )


@pytest.mark.asyncio
async def test_delete_event_file_not_found(request_mock):
    db = AsyncMock()
    db.get.return_value = None

    with patch("app.api.events.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await delete_event_file(
                uuid.uuid4(), request_mock, db, MagicMock(), MagicMock()
            )
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_semantic_search_etag_match(request_mock):
    # Patch the class method to avoid TypeError with slotted dataclass instances
    with patch("app.api.events.get_cache", return_value=MagicMock()):
        with patch(
            "app.core.cache_versioning.CacheVersionManager.get_version",
            AsyncMock(return_value="1"),
        ):
            with patch("app.api.events.format_etag", return_value='W/"match"'):
                with patch("app.api.events.etag_matches", return_value=True):
                    res = await semantic_search(
                        request_mock,
                        MagicMock(),
                        query="test",
                        if_none_match='W/"match"',
                        db=MagicMock(),
                        vector_service=MagicMock(),
                        events=MagicMock(),
                        _user=MagicMock(),
                    )
                    assert res.status_code == 304
