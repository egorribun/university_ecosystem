from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response

from app.api import events as api
from app.schemas import schemas


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        method="GET",
        headers={},
        app=SimpleNamespace(state=SimpleNamespace(cache=MagicMock())),
    )


def _user(*, role: str = "student") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _event(*, active: bool = True, ends_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_active=active,
        ends_at=ends_at or datetime.now(UTC) + timedelta(hours=1),
        image_url=None,
    )


def _event_create() -> schemas.EventCreate:
    now = datetime.now(UTC)
    return schemas.EventCreate(
        title="Closure event",
        description="Description",
        location="Room 1",
        event_type="meeting",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
    )


def _attendance_dto(user_id: uuid.UUID, event_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        event_id=event_id,
        registered_at=datetime.now(UTC),
        qr_token="token",
    )


def _result(*, rows: list[object] | None = None, scalar: object = 0) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalar.return_value = scalar
    return result


def test_id_and_cache_helpers_cover_boundaries() -> None:
    api._validate_id_type(-(2**63))
    api._validate_id_type(2**63 - 1)
    with pytest.raises(HTTPException) as exc:
        api._validate_id_type(2**63)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_event_cache_version_helpers() -> None:
    cache = MagicMock()
    with patch(
        "app.core.cache_versioning.CacheVersionManager.get_version",
        AsyncMock(return_value="v7"),
    ) as get_version:
        assert await api._get_events_list_version(cache) == "v7"
        get_version.assert_awaited_once_with(cache)

    with patch(
        "app.core.cache_versioning.CacheVersionManager.increment", AsyncMock()
    ) as increment:
        await api._increment_events_list_version(None)
        increment.assert_not_awaited()
        await api._increment_events_list_version(cache)
        increment.assert_awaited_once_with(cache)


@pytest.mark.asyncio
async def test_create_event_success_and_role_guard() -> None:
    user = _user(role="teacher")
    record = SimpleNamespace(id=uuid.uuid4())
    service = MagicMock()
    service.create_event = AsyncMock(return_value=record)
    service.serialize_event.return_value = {"id": str(record.id)}
    notifications = MagicMock()
    notifications.dispatch_event_created = AsyncMock()
    request = _request()
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "_increment_events_list_version", AsyncMock()) as bump,
    ):
        result = await api.create_event(
            _event_create(), request, MagicMock(), user, notifications, service
        )
    assert result == {"id": str(record.id)}
    bump.assert_awaited_once()
    notifications.dispatch_event_created.assert_awaited_once()

    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "_increment_events_list_version", AsyncMock()) as no_bump,
    ):
        result = await api.create_event(
            _event_create(), None, MagicMock(), user, notifications, service
        )
    assert result == {"id": str(record.id)}
    no_bump.assert_not_awaited()

    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.create_event(
                _event_create(), None, MagicMock(), _user(), notifications, service
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_all_events_and_my_events_call_services() -> None:
    user = _user()
    service = MagicMock()
    service.get_events = AsyncMock(return_value={"items": [], "total": 0})
    with patch.object(api, "resolve_locale", return_value="en"):
        result = await api.all_events.__wrapped__(
            request=_request(),
            response=Response(),
            user=user,
            search="term",
            type="meeting",
            location="Room",
            is_active=False,
            limit=7,
            cursor="cursor",
            if_none_match=None,
            events=service,
        )
    assert result == {"items": [], "total": 0}
    service.get_events.assert_awaited_once_with(
        user_id=user.id,
        search="term",
        type="meeting",
        location="Room",
        is_active=False,
        locale="en",
        limit=7,
        cursor="cursor",
    )

    service.get_my_events = AsyncMock(return_value=["mine"])
    with patch.object(api, "resolve_locale", return_value="ru"):
        result = await api.my_events.__wrapped__(
            request=_request(),
            response=Response(),
            user=user,
            if_none_match=None,
            events=service,
        )
    assert result == ["mine"]
    service.get_my_events.assert_awaited_once_with(user_id=user.id, locale="ru")


@pytest.mark.asyncio
async def test_attendance_success_lookup_and_value_errors() -> None:
    user = _user()
    event = _event()
    data = schemas.EventAttendanceCreate(event_id=event.id)
    db = AsyncMock()
    db.add = MagicMock()
    db.get.return_value = event
    service = MagicMock()
    service.register_attendance = AsyncMock(
        return_value=_attendance_dto(user.id, event.id)
    )
    with patch.object(api, "resolve_locale", return_value="en"):
        result = await api.attend(data, _request(), db, user, service)
    assert result.event_id == event.id

    for error in (LookupError(), ValueError()):
        service.register_attendance = AsyncMock(side_effect=error)
        with patch.object(api, "resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as exc:
                await api.attend(data, _request(), db, user, service)
        assert exc.value.status_code in (404, 409)


@pytest.mark.asyncio
async def test_unregister_event_delegates() -> None:
    user = _user()
    data = schemas.EventAttendanceCreate(event_id=uuid.uuid4())
    service = MagicMock()
    service.unregister_attendance = AsyncMock(return_value={"ok": True})
    assert await api.unregister_event(data, user, service) == {"ok": True}
    service.unregister_attendance.assert_awaited_once_with(data, user_id=user.id)


@pytest.mark.asyncio
async def test_upload_event_file_commit_and_refresh_cleanup() -> None:
    event = _event()
    user = _user(role="teacher")
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    file = SimpleNamespace(size=10)

    db = AsyncMock()
    db.add = MagicMock()
    db.get.return_value = event
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "scan_for_malware", AsyncMock()),
        patch.object(api, "save_attachment", AsyncMock(return_value="/file.txt")),
    ):
        result = await api.upload_event_file(
            event.id, file, request=None, db=db, user=user, checker=checker
        )
    assert result.file_url == "/file.txt"

    for failure, method in (("commit", "commit"), ("refresh", "refresh")):
        db = AsyncMock()
        db.add = MagicMock()
        db.get.return_value = event
        if failure == "commit":
            db.commit.side_effect = RuntimeError("commit")
        else:
            db.refresh.side_effect = RuntimeError("refresh")
        with (
            patch.object(api, "resolve_locale", return_value="en"),
            patch.object(api, "scan_for_malware", AsyncMock()),
            patch.object(api, "save_attachment", AsyncMock(return_value="/file.txt")),
            patch.object(api, "delete_static_file", AsyncMock()) as cleanup,
        ):
            with pytest.raises(RuntimeError):
                await api.upload_event_file(
                    event.id, file, request=None, db=db, user=user, checker=checker
                )
        cleanup.assert_awaited_once_with("/file.txt")
        if method == "commit":
            db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_event_files_and_upload_image_paths() -> None:
    event_id = uuid.uuid4()
    db = AsyncMock()
    files = [SimpleNamespace(id=uuid.uuid4())]
    db.execute.return_value = _result(rows=files)
    assert await api.get_event_files(event_id, db) == files

    event = _event()
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    file = SimpleNamespace(size=4)
    db = AsyncMock()
    db.get.return_value = event
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "scan_for_malware", AsyncMock()),
        patch.object(
            api, "save_upload", AsyncMock(return_value="/static/tmp/event-image.png")
        ),
    ):
        result = await api.upload_event_image(
            file,
            request=_request(),
            user=_user(role="teacher"),
            event_id=event.id,
            db=db,
            checker=checker,
        )
    assert result == {"url": "/static/tmp/event-image.png"}

    checker.check_permission = AsyncMock(return_value=False)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.upload_event_image(
                file,
                request=_request(),
                user=_user(role="teacher"),
                event_id=event.id,
                db=db,
                checker=checker,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_image_cleanup_and_missing_event() -> None:
    event_id = uuid.uuid4()
    event = _event()
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    db = AsyncMock()
    db.get.return_value = event
    file = SimpleNamespace(size=4)

    db = AsyncMock()
    db.get.return_value = event
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "scan_for_malware", AsyncMock()),
        patch.object(api, "save_upload", AsyncMock(side_effect=RuntimeError("save"))),
        patch.object(api, "delete_static_file", AsyncMock()) as delete,
    ):
        with pytest.raises(RuntimeError):
            await api.upload_event_image(
                file,
                request=_request(),
                user=_user(role="teacher"),
                event_id=event_id,
                db=db,
                checker=checker,
            )
    delete.assert_not_awaited()

    db = AsyncMock()
    db.get.return_value = None
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.upload_event_image(
                file,
                request=_request(),
                user=_user(role="teacher"),
                event_id=event_id,
                db=db,
                checker=checker,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_event_success_permissions_and_errors() -> None:
    event_id = uuid.uuid4()
    user = _user(role="teacher")
    existing = _event()
    existing.image_url = "/old.png"
    updated = _event()
    updated.id = event_id
    updated.image_url = "/new.png"
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    service = MagicMock()
    service.update_event = AsyncMock(return_value=updated)
    service.serialize_event.return_value = {"id": str(event_id)}
    db = AsyncMock()
    db.get.return_value = existing
    db.execute.side_effect = [_result(rows=[]), _result(scalar=3)]
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "delete_static_file", AsyncMock()) as delete,
    ):
        result = await api.update_event(
            event_id, schemas.EventUpdate(), None, db, user, service, checker
        )
    assert result == {"id": str(event_id)}
    delete.assert_awaited_once_with("/old.png")
    assert service.serialize_event.call_args.kwargs["participant_count"] == 3

    existing.image_url = "/same.png"
    updated.image_url = "/same.png"
    db = AsyncMock()
    db.get.return_value = existing
    db.execute.side_effect = [_result(rows=[]), _result(scalar=0)]
    service.update_event = AsyncMock(return_value=updated)
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "_increment_events_list_version", AsyncMock()) as bump,
    ):
        result = await api.update_event(
            event_id, schemas.EventUpdate(), _request(), db, user, service, checker
        )
    assert result == {"id": str(event_id)}
    bump.assert_awaited_once()

    checker.check_permission = AsyncMock(return_value=False)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.update_event(
                event_id, schemas.EventUpdate(), None, db, user, service, checker
            )
    assert exc.value.status_code == 403

    checker.check_permission = AsyncMock(return_value=True)
    service.update_event = AsyncMock(side_effect=ValueError("invalid update"))
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.update_event(
                event_id, schemas.EventUpdate(), None, db, user, service, checker
            )
    assert exc.value.status_code == 400

    db.get.return_value = existing
    service.update_event = AsyncMock(return_value=updated)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.update_event(
                1, schemas.EventUpdate(), None, db, user, service, checker
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_and_get_event_paths() -> None:
    event_id = uuid.uuid4()
    user = _user(role="teacher")
    event = _event()
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    service = MagicMock()
    service.get_event_by_id = AsyncMock(return_value=event)
    service.delete_event = AsyncMock()
    with patch.object(api, "resolve_locale", return_value="en"):
        assert await api.delete_event(event_id, None, service, user, checker) == {
            "ok": True
        }
    service.delete_event.assert_awaited_once_with(event_id)

    service.get_event_by_id = AsyncMock(return_value=event)
    checker.check_permission = AsyncMock(return_value=True)
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "_increment_events_list_version", AsyncMock()) as bump,
    ):
        assert await api.delete_event(event_id, _request(), service, user, checker) == {
            "ok": True
        }
    bump.assert_awaited_once()

    checker.check_permission = AsyncMock(return_value=False)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_event(event_id, None, service, user, checker)
    assert exc.value.status_code == 403

    service.get_event_by_id = AsyncMock(return_value=None)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_event(event_id, None, service, user, checker)
    assert exc.value.status_code == 404

    service.get_event_detail = AsyncMock(return_value={"id": str(event_id)})
    with patch.object(api, "resolve_locale", return_value="en"):
        result = await api.get_event.__wrapped__(
            event_id, None, Response(), user, None, service
        )
    assert result == {"id": str(event_id)}

    service.get_event_detail = AsyncMock(return_value=None)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.get_event.__wrapped__(
                event_id, None, Response(), user, None, service
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_event_file_success_parent_guard_and_permission() -> None:
    file_id = uuid.uuid4()
    event = _event()
    record = SimpleNamespace(event_id=event.id, file_url="/file.txt")
    user = _user(role="teacher")
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    db = AsyncMock()
    db.get.side_effect = [record, event]
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "delete_static_file", AsyncMock()) as delete,
    ):
        assert await api.delete_event_file(file_id, None, db, user, checker) == {
            "ok": True
        }
    delete.assert_awaited_once_with("/file.txt")
    db.delete.assert_awaited_once_with(record)
    db.commit.assert_awaited_once()

    db = AsyncMock()
    db.get.side_effect = [record, None]
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_event_file(file_id, None, db, user, checker)
    assert exc.value.status_code == 404

    db = AsyncMock()
    db.get.side_effect = [record, event]
    checker.check_permission = AsyncMock(return_value=False)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_event_file(file_id, None, db, user, checker)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_semantic_search_full_and_event_etag() -> None:
    query_event = SimpleNamespace(id=uuid.uuid4())
    vector = MagicMock()
    vector.get_embedding = AsyncMock(return_value=[0.1, 0.2])
    vector.search_similar = AsyncMock(return_value=[query_event])
    service = MagicMock()
    service.serialize_event.return_value = {"id": str(query_event.id)}
    response = Response()
    cache = MagicMock()
    with (
        patch.object(api, "resolve_locale", return_value="ru"),
        patch.object(api, "normalize_locale", return_value="ru"),
        patch.object(api, "get_cache", return_value=cache),
        patch.object(api, "_get_events_list_version", AsyncMock(return_value="v1")),
        patch.object(api, "format_etag", return_value='"etag"'),
        patch.object(api, "etag_matches", return_value=False),
    ):
        result = await api.semantic_search(
            _request(),
            response,
            query="term",
            limit=5,
            min_score=0.7,
            if_none_match=None,
            db=AsyncMock(),
            vector_service=vector,
            events=service,
            _user=_user(),
        )
    assert result == [{"id": str(query_event.id)}]
    assert response.headers["ETag"] == '"etag"'
    assert response.headers["Content-Language"] == "ru"
    vector.get_embedding.assert_awaited_once_with("term")
