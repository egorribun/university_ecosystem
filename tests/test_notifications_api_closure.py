from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError

from app.api import notifications as api


def _user(*, group_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), group_id=group_id)


def _request() -> SimpleNamespace:
    return SimpleNamespace(headers={})


def _notification(user_id: uuid.UUID, *, read: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Title",
        body="Body",
        type="system",
        url="/notifications",
        read=read,
        read_at=datetime.now(UTC) if read else None,
    )


def _db_result(value: object = None, *, rowcount: int | None = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    if rowcount is not None:
        result.rowcount = rowcount
    return result


def _row(
    user_id: uuid.UUID, *, identifier: uuid.UUID | None = None
) -> dict[str, object]:
    return {
        "id": identifier or uuid.uuid4(),
        "user_id": user_id,
        "title": "Title",
        "title_en": "English title",
        "body": "Body",
        "body_en": "English body",
        "type": "system",
        "url": "/notifications",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "read": False,
        "read_at": None,
    }


def test_notification_helpers_cover_edge_inputs() -> None:
    assert api._parse_datetime(1704067200) is not None
    assert api._parse_datetime("1704067200000") is not None
    assert api._parse_datetime("1704067200") is not None
    assert api._parse_datetime("2026-01-01T00:00:00") is not None
    assert api._parse_datetime("not-a-date") is None
    assert api._parse_datetime("   ") is None
    assert api._parse_datetime("1e30") is None
    assert api._parse_datetime(1e30) is None
    assert api._parse_datetime(object()) is None
    assert api._parse_datetime(datetime(2026, 1, 1)) is not None

    class BadString:
        def __str__(self) -> str:
            raise RuntimeError("cannot stringify")

    assert api._coerce_int(BadString(), default=7) == 7
    assert api._coerce_int(" ", default=7) == 7
    assert api._coerce_int("1.5") == 1
    assert api._coerce_int(None, default=7) == 7
    assert api._coerce_int(True) == 1
    assert api._coerce_int(4) == 4
    assert api._coerce_int(4.5) == 4
    assert api._coerce_int("not-a-number", default=7) == 7
    assert api._coerce_bool(0) is False
    assert api._coerce_bool(object()) is True
    assert api._coerce_bool("off") is False
    assert api._coerce_bool(" maybe ") is True


def test_localized_field_required_and_fallback_paths() -> None:
    with patch("app.api.notifications.localized_text", return_value=None):
        assert (
            api._localized_notification_field("en", "RU", None, required=True) == "RU"
        )
        assert (
            api._localized_notification_field("en", "  ", "EN", required=True) == "EN"
        )
        assert api._localized_notification_field("en", None, None, required=True) == ""
        assert (
            api._localized_notification_field("en", "RU", None, required=False) == "RU"
        )


def test_serialize_notification_mapping_and_orm_fallback() -> None:
    user_id = uuid.uuid4()
    row = _row(user_id)
    serialized = api._serialize_notification(row, locale="en")
    assert serialized.title == "English title"
    assert serialized.body == "English body"
    assert serialized.read is False

    orm = SimpleNamespace(**row)
    orm.read = "true"
    serialized_orm = api._serialize_notification(orm, locale="ru")
    assert serialized_orm.title == "Title"
    assert serialized_orm.read is True

    invalid = dict(row)
    invalid["id"] = "not-a-uuid"
    with patch.object(api.logger, "warning") as warning:
        fallback = api._serialize_notification(invalid, locale="en")
    assert fallback.id == "not-a-uuid"
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_existing_columns_bind_and_table_paths() -> None:
    db = AsyncMock()
    sync_session = SimpleNamespace(bind=None)

    async def run_sync_no_bind(fn):
        return fn(sync_session)

    db.run_sync = run_sync_no_bind
    assert await api._existing_notification_columns(db) == set()

    sync_session.bind = object()

    async def run_sync_no_table(fn):
        with patch("app.api.notifications.inspect") as inspector:
            inspector.return_value.get_columns.side_effect = NoSuchTableError("missing")
            return fn(sync_session)

    db.run_sync = run_sync_no_table
    assert await api._existing_notification_columns(db) == set()

    async def run_sync_columns(fn):
        with patch("app.api.notifications.inspect") as inspector:
            inspector.return_value.get_columns.return_value = [
                {"name": "id"},
                {"name": "read"},
            ]
            return fn(sync_session)

    db.run_sync = run_sync_columns
    assert await api._existing_notification_columns(db) == {"id", "read"}


@pytest.mark.asyncio
async def test_fetch_rows_primary_success_and_error_paths() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"id": 1}]
    db.execute.return_value = result

    rows, columns = await api._fetch_notification_rows(db, uuid.uuid4(), 5, None)
    assert rows == [{"id": 1}]
    assert columns is None

    cursor = (datetime(2026, 1, 1, tzinfo=UTC), str(uuid.uuid4()))
    rows, columns = await api._fetch_notification_rows(db, uuid.uuid4(), 5, cursor)
    assert rows == [{"id": 1}]
    assert columns is None

    db.execute.side_effect = ValueError("bad cast")
    with patch.object(
        api,
        "_fetch_notification_rows_fallback",
        AsyncMock(return_value=([], set())),
    ) as fallback:
        assert await api._fetch_notification_rows(db, uuid.uuid4(), 5, None) == (
            [],
            set(),
        )
        fallback.assert_awaited_once()

    db.execute.side_effect = SQLAlchemyError("syntax error")
    with pytest.raises(SQLAlchemyError):
        await api._fetch_notification_rows(db, uuid.uuid4(), 5, None)

    db.execute.side_effect = SQLAlchemyError("no such column: notification.body_en")
    with patch.object(
        api,
        "_fetch_notification_rows_fallback",
        AsyncMock(return_value=([], {"id", "user_id"})),
    ) as fallback:
        assert await api._fetch_notification_rows(db, uuid.uuid4(), 5, None) == (
            [],
            {"id", "user_id"},
        )
        fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_rows_fallback_schema_variants() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"id": 1}]
    db.execute.return_value = result
    user_id = uuid.uuid4()
    cursor = (datetime(2026, 1, 1, tzinfo=UTC), str(uuid.uuid4()))

    with patch.object(
        api, "_existing_notification_columns", AsyncMock(return_value=set())
    ):
        assert await api._fetch_notification_rows_fallback(db, user_id, 5, None) == (
            [],
            set(),
        )

    with patch.object(
        api,
        "_existing_notification_columns",
        AsyncMock(return_value={"id", "user_id"}),
    ):
        rows, columns = await api._fetch_notification_rows_fallback(
            db, user_id, 5, None
        )
        assert rows == [{"id": 1}]
        assert columns == {"id", "user_id"}

    with patch.object(
        api,
        "_existing_notification_columns",
        AsyncMock(return_value={"id", "user_id"}),
    ):
        rows, columns = await api._fetch_notification_rows_fallback(
            db, user_id, 5, cursor
        )
    assert rows == [{"id": 1}]
    assert columns == {"id", "user_id"}

    available = {"id", "user_id", "created_at", "read"}
    with patch.object(
        api, "_existing_notification_columns", AsyncMock(return_value=available)
    ):
        rows, columns = await api._fetch_notification_rows_fallback(
            db, user_id, 5, cursor
        )
    assert rows == [{"id": 1}]
    assert columns == available


@pytest.mark.asyncio
async def test_list_notifications_headers_cursor_and_empty_schema() -> None:
    user = _user()
    response = Response()
    db = AsyncMock()
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api, "_fetch_notification_rows", AsyncMock(return_value=([], set()))
        ),
    ):
        result = await api.list_notifications(
            _request(), response, db=db, user=user, cursor=None, limit=20
        )
    assert result.items == []
    assert result.unread_count == 0
    assert response.headers["Content-Language"] == "en"
    assert "Accept-Language" in response.headers["Vary"]
    assert response.headers["Cache-Control"] == "no-store, max-age=0"

    bad_cursor = base64.b64encode(b"2026-01-01T00:00:00,not-a-uuid").decode()
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.list_notifications(
                _request(), Response(), db=db, user=user, cursor=bad_cursor
            )
    assert exc.value.status_code == 400

    valid_shape_bad_id = api._encode_cursor(
        datetime(2026, 1, 1, tzinfo=UTC), "not-a-uuid"
    )
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.list_notifications(
                _request(),
                Response(),
                db=db,
                user=user,
                cursor=valid_shape_bad_id,
                limit=20,
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_notifications_unread_count_and_next_cursor() -> None:
    user = _user()
    rows = [_row(user.id), _row(user.id)]
    db = AsyncMock()
    db.execute.return_value = _db_result(3)
    cursor_dt = datetime(2026, 1, 1, tzinfo=UTC)
    cursor = api._encode_cursor(cursor_dt, uuid.uuid4())
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api,
            "_fetch_notification_rows",
            AsyncMock(return_value=(rows, {"read", "id", "user_id"})),
        ) as fetch,
    ):
        result = await api.list_notifications(
            _request(), Response(), db=db, user=user, cursor=cursor, limit=1
        )
    assert len(result.items) == 1
    assert result.unread_count == 3
    assert result.has_more is True
    assert result.next_cursor is not None
    assert fetch.await_args.args[3] is not None


@pytest.mark.asyncio
async def test_list_notifications_count_fallback_branches() -> None:
    user = _user()
    rows = [_row(user.id)]

    db = AsyncMock()
    db.execute.side_effect = SQLAlchemyError("no such column: read")
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api,
            "_fetch_notification_rows",
            AsyncMock(return_value=(rows, {"read", "id"})),
        ),
    ):
        result = await api.list_notifications(
            _request(), Response(), db=db, user=user, cursor=None, limit=20
        )
    assert result.unread_count == 1

    db = AsyncMock()
    db.execute.side_effect = SQLAlchemyError("database unavailable")
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api,
            "_fetch_notification_rows",
            AsyncMock(return_value=(rows, {"id", "user_id"})),
        ),
    ):
        result = await api.list_notifications(
            _request(), Response(), db=db, user=user, cursor=None, limit=20
        )
    assert result.unread_count == 1

    db = AsyncMock()
    db.execute.side_effect = SQLAlchemyError("database unavailable")
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api,
            "_fetch_notification_rows",
            AsyncMock(return_value=(rows, {"read", "id"})),
        ),
    ):
        with pytest.raises(SQLAlchemyError):
            await api.list_notifications(
                _request(), Response(), db=db, user=user, cursor=None, limit=20
            )


@pytest.mark.asyncio
async def test_mark_read_single_all_read_and_not_found_paths() -> None:
    user = _user()
    request = _request()

    already = _notification(user.id, read=True)
    db = AsyncMock()
    db.execute.return_value = _db_result(already)
    with patch.object(api, "resolve_locale", return_value="en"):
        assert await api.mark_read_single(already.id, request, db=db, user=user) == {
            "ok": True
        }
    db.commit.assert_not_awaited()

    unread = _notification(user.id)
    db = AsyncMock()
    db.execute.return_value = _db_result(unread)
    with patch.object(api, "resolve_locale", return_value="en"):
        assert await api.mark_read_single(unread.id, request, db=db, user=user) == {
            "ok": True
        }
    assert unread.read is True
    assert unread.read_at is not None
    db.commit.assert_awaited_once()

    other = _notification(uuid.uuid4())
    db = AsyncMock()
    db.execute.return_value = _db_result(other)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.mark_read_single(other.id, request, db=db, user=user)
    assert exc.value.status_code == 404

    db = AsyncMock()
    db.execute.return_value = _db_result(None)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.mark_read_single(uuid.uuid4(), request, db=db, user=user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read_rowcount_and_missing_rowcount() -> None:
    user = _user()
    db = AsyncMock()
    db.execute.return_value = _db_result(rowcount=4)
    assert await api.mark_all_read(db=db, user=user) == {"ok": True, "updated": 4}
    db.commit.assert_awaited_once()

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace()
    assert await api.mark_all_read(db=db, user=user) == {"ok": True, "updated": 0}


@pytest.mark.asyncio
async def test_delete_and_clear_notification_paths() -> None:
    user = _user()
    request = _request()
    notification = _notification(user.id)
    db = AsyncMock()
    db.execute.return_value = _db_result(notification)
    with patch.object(api, "resolve_locale", return_value="en"):
        assert await api.delete_notification(
            notification.id, request, db=db, user=user
        ) == {"ok": True}
    db.delete.assert_awaited_once_with(notification)
    db.commit.assert_awaited_once()

    other = _notification(uuid.uuid4())
    db = AsyncMock()
    db.execute.return_value = _db_result(other)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_notification(other.id, request, db=db, user=user)
    assert exc.value.status_code == 404

    db = AsyncMock()
    db.execute.return_value = _db_result(None)
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.delete_notification(uuid.uuid4(), request, db=db, user=user)
    assert exc.value.status_code == 404

    db = AsyncMock()
    db.execute.return_value = _db_result(rowcount=2)
    assert await api.clear_notifications(db=db, user=user) == {
        "ok": True,
        "deleted": 2,
    }

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace()
    assert await api.clear_notifications(db=db, user=user) == {
        "ok": True,
        "deleted": 0,
    }


@pytest.mark.asyncio
async def test_check_schedule_without_group_delegates_to_list() -> None:
    user = _user()
    response = Response()
    expected = object()
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api, "list_notifications", AsyncMock(return_value=expected)
        ) as listed,
    ):
        result = await api.check_schedule_and_generate(
            _request(), response, db=AsyncMock(), user=user
        )
    assert result is expected
    listed.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_schedule_skips_duplicate_and_creates_new() -> None:
    user = _user(group_id=uuid.uuid4())
    response = Response()
    lesson_one = SimpleNamespace(id=uuid.uuid4())
    lesson_two = SimpleNamespace(id=uuid.uuid4())
    lessons_result = MagicMock()
    lessons_result.scalars.return_value.all.return_value = [lesson_one, lesson_two]
    duplicate = _db_result(1)
    new = _db_result(0)
    db = AsyncMock()
    db.execute.side_effect = [lessons_result, duplicate, new]
    expected = object()
    message_one = (
        "Title",
        "Body",
        "tag",
        {"kind": "schedule"},
        {"en": "Title"},
        {"en": "Body"},
        "dedupe",
    )
    message_two = ("", "Body", None, {}, {}, {}, "")
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(
            api,
            "build_schedule_reminder_message",
            side_effect=[message_one, message_two],
        ),
        patch.object(api, "create_notifications_for_users", AsyncMock()) as create,
        patch.object(api, "translate", return_value="Open schedule"),
        patch.object(api, "list_notifications", AsyncMock(return_value=expected)),
    ):
        result = await api.check_schedule_and_generate(
            _request(), response, db=db, user=user, lookahead_minutes=15
        )
    assert result is expected
    create.assert_awaited_once()
    assert create.await_args.kwargs["dedupe_key"] == ""


@pytest.mark.asyncio
async def test_check_schedule_uses_scalar_one_legacy_count_fallback() -> None:
    user = _user(group_id=uuid.uuid4())
    response = Response()
    lesson = SimpleNamespace(id=uuid.uuid4())
    lessons_result = MagicMock()
    lessons_result.scalars.return_value.all.return_value = [lesson]
    legacy_count = MagicMock()
    legacy_count.scalar_one_or_none.return_value = None
    legacy_count.scalar_one.return_value = 0
    expected = object()
    message = (
        "Title",
        "Body",
        "tag",
        {"kind": "schedule"},
        {"en": "Title"},
        {"en": "Body"},
        "dedupe",
    )
    db = AsyncMock()
    db.execute.side_effect = [lessons_result, legacy_count]

    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch.object(api, "build_schedule_reminder_message", return_value=message),
        patch.object(api, "create_notifications_for_users", AsyncMock()) as create,
        patch.object(api, "translate", return_value="Open schedule"),
        patch.object(api, "list_notifications", AsyncMock(return_value=expected)),
    ):
        result = await api.check_schedule_and_generate(
            _request(), response, db=db, user=user, lookahead_minutes=15
        )

    assert result is expected
    create.assert_awaited_once()
