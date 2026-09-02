from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import (
    String,
    and_,
    delete,
    desc,
    func,
    inspect,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError

from app.api.deps import get_current_user
from app.api.validation import ensure_exists, raise_not_found, raise_validation_error
from app.core.database import get_db, get_read_db
from app.core.localization import localized_text, resolve_locale, translate
from app.core.logging import get_logger
from app.core.middleware import _ensure_vary_header as ensure_vary_header
from app.core.notification_contract import (
    build_notification_metadata,
    infer_notification_topic,
)
from app.core.protocols import AsyncDatabaseSession
from app.models import Notification, Schedule, User
from app.schemas.schemas import (
    NotificationOut,
    NotificationsListOut,
)
from app.services.notifications import (
    build_schedule_reminder_message,
    create_notifications_for_users,
)
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


_MISSING_COLUMN_MARKERS = (
    "no such column",
    "unknown column",
    "does not exist",
    "undefined column",
)


def _is_missing_column_error(exc: SQLAlchemyError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return any(marker in message for marker in _MISSING_COLUMN_MARKERS)


def _ensure_vary_header(response: Response, header_name: str) -> None:
    ensure_vary_header(response, header_name)


def _parse_datetime(value: Any) -> datetime | None:
    """Attempt to coerce various inputs into an aware UTC datetime."""

    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    if isinstance(value, int | float):
        numeric = value
        if numeric > 1e12:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, UTC)
        except (OverflowError, OSError, ValueError):  # RZ-28-01
            return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        candidate = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            try:
                numeric = float(text)
            except ValueError:
                return None
            if numeric > 1e12:
                numeric /= 1000.0
            try:
                return datetime.fromtimestamp(numeric, UTC)
            except (OverflowError, OSError, ValueError):  # RZ-28-01
                return None
        else:
            return (
                parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            )

    return None


def _ensure_utc(dt: Any) -> datetime:
    """Normalize datetimes from the database to aware UTC values."""

    parsed = _parse_datetime(dt)
    return parsed or datetime.now(UTC)


def _coerce_bool(value: Any) -> bool:
    """Best-effort conversion of various inputs to booleans."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off"}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    """Coerce arbitrary values to integers, falling back to ``default``."""

    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
    except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — safe int parsing returns default (reviewed TD-27-04)
        return default
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except (TypeError, ValueError):  # RZ-28-01
            return default


def _encode_cursor(dt: datetime, nid: uuid.UUID | int | str) -> str:
    aware = _ensure_utc(dt)
    return encode_datetime_cursor(aware, str(nid))


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    result = decode_datetime_cursor(value)
    if result is None:
        return None
    dt, id_str = result
    return dt, id_str


def _localized_notification_field(
    locale: str | None,
    ru_value: str | None,
    en_value: str | None,
    *,
    required: bool = False,
) -> str | None:
    value = localized_text(locale, ru=ru_value, en=en_value)
    if value is not None:
        return value
    if required:
        if isinstance(ru_value, str) and ru_value.strip():
            return ru_value
        if isinstance(en_value, str) and en_value.strip():
            return en_value
        return ru_value or en_value or ""
    return ru_value or en_value


async def _existing_notification_columns(db: AsyncDatabaseSession) -> set[str]:
    def _sync_get_columns(sync_session: Any) -> set[str]:
        bind = sync_session.bind
        if bind is None:
            return set()
        inspector = inspect(bind)
        try:
            columns = inspector.get_columns(Notification.__tablename__)
        except NoSuchTableError:
            return set()
        return {column["name"] for column in columns}

    return await db.run_sync(_sync_get_columns)


async def _fetch_notification_rows(
    db: AsyncDatabaseSession,
    user_id: uuid.UUID | int | str,
    limit: int,
    cursor_info: tuple[datetime, str] | None,
) -> tuple[list[Mapping[str, Any]], set[str] | None]:
    table = Notification.__table__
    cols = table.c
    where = [cols.user_id == user_id]
    if cursor_info:
        cursor_dt, cursor_id = cursor_info
        # cursor_id is always UUID-validated at the route level (P2-W5-16).
        target_id: uuid.UUID | str | int = (
            uuid.UUID(cursor_id) if isinstance(cursor_id, str) else cursor_id
        )
        where.append(
            or_(
                cols.created_at < cursor_dt,
                and_(cols.created_at == cursor_dt, cols.id < target_id),
            )
        )
    stmt = (
        select(
            cols.id,
            cols.title,
            cols.title_en,
            cols.body,
            cols.body_en,
            cols.type,
            cols.url,
            cols.created_at.cast(String).label("created_at"),
            cols.read,
            cols.read_at.cast(String).label("read_at"),
        )
        .where(and_(*where))
        .order_by(desc(cols.created_at), desc(cols.id))
        .limit(limit + 1)
    )
    try:
        rows = (await db.execute(stmt)).mappings().all()
        return cast(list[Mapping[str, Any]], rows), None
    except SQLAlchemyError as exc:
        if not _is_missing_column_error(exc):
            raise
    except ValueError:
        return await _fetch_notification_rows_fallback(db, user_id, limit, cursor_info)
    return await _fetch_notification_rows_fallback(db, user_id, limit, cursor_info)


async def _fetch_notification_rows_fallback(
    db: AsyncDatabaseSession,
    user_id: uuid.UUID | int | str,
    limit: int,
    cursor_info: tuple[datetime, str] | None,
) -> tuple[list[Mapping[str, Any]], set[str]]:
    available = await _existing_notification_columns(db)
    if not available or "id" not in available or "user_id" not in available:
        return [], available

    table = Notification.__table__
    cols = table.c

    def column(name: str, *, default: Any = None) -> Any:
        if name in available:
            column_obj = cols[name]
            if name in {"created_at", "read_at"}:
                return column_obj.cast(String).label(name)
            return column_obj
        return literal(default).label(name)

    where = [cols.user_id == user_id]
    if cursor_info:
        cursor_dt, cursor_id = cursor_info
        # cursor_id is always UUID-validated at the route level (P2-W5-16).
        target_id: uuid.UUID | str | int = (
            uuid.UUID(cursor_id) if isinstance(cursor_id, str) else cursor_id
        )

        if "created_at" in available:
            where.append(
                or_(
                    cols.created_at < cursor_dt,
                    and_(cols.created_at == cursor_dt, cols.id < target_id),
                )
            )
        else:
            where.append(cols.id < target_id)

    order_by_clauses = []
    if "created_at" in available:
        order_by_clauses.append(desc(cols.created_at))
    order_by_clauses.append(desc(cols.id))

    stmt = (
        select(
            column("id"),
            column("title"),
            column("title_en"),
            column("body"),
            column("body_en"),
            column("type"),
            column("url"),
            column("created_at"),
            column("read", default=False),
            column("read_at"),
        )
        .where(and_(*where))
        .order_by(*order_by_clauses)
        .limit(limit + 1)
    )
    rows = (await db.execute(stmt)).mappings().all()
    return cast(list[Mapping[str, Any]], rows), available


def _serialize_notification(
    record: Notification | Mapping[str, Any], locale: str | None
) -> NotificationOut:
    if isinstance(record, Mapping):
        getter = record.get
    else:
        # ``getattr`` gracefully falls back to a default value, unlike
        # ``object.__getattribute__`` which expects only the attribute name.
        # Using a small wrapper keeps the ``getter`` interface consistent for
        # mapping and ORM objects alike, preventing ``TypeError`` when
        # additional arguments are supplied (as ``dict.get`` supports).
        def getter(key: str, default: Any = None) -> Any:
            return getattr(record, key, default)

    created_at = _ensure_utc(getter("created_at", None))
    read_at_raw = getter("read_at", None)
    read_at = _parse_datetime(read_at_raw) if read_at_raw else None
    type_raw = getter("type", None)
    url_raw = getter("url", None)
    identifier = getter("id")
    if isinstance(identifier, str):
        identifier = identifier.strip()

    topic = infer_notification_topic(type_raw)
    metadata = build_notification_metadata(
        notification_id=identifier,
        topic=topic,
        notification_type=str(type_raw) if type_raw is not None else None,
        url=str(url_raw) if url_raw is not None else None,
    )
    data = {
        "id": identifier,
        "title": _localized_notification_field(
            locale,
            getter("title", None),
            getter("title_en", None),
            required=True,
        ),
        "body": _localized_notification_field(
            locale,
            getter("body", None),
            getter("body_en", None),
        ),
        "title_en": getter("title_en", None),
        "body_en": getter("body_en", None),
        "type": type_raw,
        "url": url_raw,
        "topic": topic,
        "metadata": metadata,
        "created_at": created_at,
        "read": _coerce_bool(getter("read", False)),
        "read_at": read_at,
    }
    try:
        return NotificationOut.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "Failed to validate notification payload for id=%s: %s", identifier, exc
        )
        return NotificationOut.model_construct(**data)


@router.get("", response_model=NotificationsListOut)
async def list_notifications(
    request: Request,
    response: Response,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncDatabaseSession = Depends(get_read_db),
    user: User = Depends(get_current_user),
) -> NotificationsListOut:
    locale = resolve_locale(request=request, user=user)
    response.headers["Content-Language"] = locale or ""
    _ensure_vary_header(response, "Accept-Language")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    cursor_info: tuple[datetime, str] | None = None
    if cursor:
        parsed = _decode_cursor(cursor)
        if not parsed:
            raise_validation_error("errors.notifications.bad_cursor", locale)
        cursor_dt, cursor_id = parsed
        # P2-W5-16: Strictly validate cursor_id as a UUID before letting it
        # reach the SQL query; a non-UUID string compared to a UUID column can
        # cause type confusion or unexpected DB cast behaviour.
        try:
            uuid.UUID(str(cursor_id))
        except (ValueError, AttributeError):  # RZ-28-01
            raise_validation_error("errors.notifications.bad_cursor", locale)
        cursor_info = (_ensure_utc(cursor_dt), cursor_id)

    rows, available_columns = await _fetch_notification_rows(
        db, user.id, limit, cursor_info
    )
    items = rows[:limit]
    has_more = len(rows) > limit

    unread = 0
    if available_columns == set():
        unread = 0
    elif available_columns is None or "read" in available_columns:
        q_unread = select(func.count(Notification.id)).where(
            and_(Notification.user_id == user.id, Notification.read.is_(False))
        )
        try:
            unread = (await db.execute(q_unread)).scalar_one() or 0
        except SQLAlchemyError as exc:
            if not _is_missing_column_error(exc):
                raise
            logger.warning(
                "Falling back to row-based unread count due to schema mismatch",
                extra={"error": str(exc), "user_id": str(user.id)},
            )
            unread = sum(1 for row in rows if not _coerce_bool(row.get("read", False)))
    else:
        count_stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user.id
        )
        try:
            unread = (await db.execute(count_stmt)).scalar_one() or 0
        except SQLAlchemyError as exc:
            logger.warning(
                "Falling back to row-based total count due to SQLAlchemy error",
                extra={"error": str(exc), "user_id": str(user.id)},
            )
            unread = sum(1 for row in rows if not _coerce_bool(row.get("read", False)))

    next_cursor = None
    if items and has_more:
        last = items[-1]
        last_created = _ensure_utc(last["created_at"])
        last_id = last["id"]
        next_cursor = _encode_cursor(last_created, last_id)

    return NotificationsListOut(
        items=[_serialize_notification(n, locale) for n in items],
        unread_count=int(unread),
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.patch("/{notif_id}/read")
async def mark_read_single(
    notif_id: uuid.UUID,
    request: Request,
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    notif = (
        await db.execute(select(Notification).where(Notification.id == notif_id))
    ).scalar_one_or_none()
    ensure_exists(notif, "notifications", locale)
    assert notif is not None  # noqa: S101

    if notif.user_id != user.id:
        raise_not_found("notifications", locale)

    if notif.read:
        return {"ok": True}

    from typing import cast

    notif.read = cast(Any, True)
    notif.read_at = cast(Any, datetime.now(UTC))
    await db.commit()

    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == user.id, Notification.read.is_(False)))
        .values(read=True, read_at=now)
    )
    await db.commit()
    updated = getattr(result, "rowcount", 0)
    return {"ok": True, "updated": int(updated)}


@router.delete("/{notif_id}")
async def delete_notification(
    notif_id: uuid.UUID,
    request: Request,
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    notif = (
        await db.execute(select(Notification).where(Notification.id == notif_id))
    ).scalar_one_or_none()
    ensure_exists(notif, "notifications", locale)
    assert notif is not None  # noqa: S101

    if notif.user_id != user.id:
        raise_not_found("notifications", locale)

    await db.delete(notif)
    await db.commit()

    return {"ok": True}


@router.delete("")
async def clear_notifications(
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    result = await db.execute(
        delete(Notification).where(Notification.user_id == user.id)
    )
    await db.commit()
    deleted = getattr(result, "rowcount", 0)
    return {"ok": True, "deleted": int(deleted)}


@router.post("/check-schedule", response_model=NotificationsListOut)
async def check_schedule_and_generate(
    request: Request,
    response: Response,
    lookahead_minutes: int = Query(15, ge=1, le=180),
    db: AsyncDatabaseSession = Depends(
        get_db
    ),  # RZ-W19-14: write DB — this endpoint creates notifications
    user: User = Depends(get_current_user),
) -> NotificationsListOut:
    locale = resolve_locale(request=request, user=user)
    if not user.group_id:
        return await list_notifications(
            request=request, response=response, db=db, user=user, limit=20, cursor=None
        )

    now = datetime.now(UTC)
    soon = now + timedelta(minutes=lookahead_minutes)

    q = (
        select(Schedule)
        .where(
            and_(
                Schedule.group_id == user.group_id,
                Schedule.start_time >= now,
                Schedule.start_time <= soon,
            )
        )
        .order_by(Schedule.start_time.asc())
    )
    lessons = (await db.execute(q)).scalars().all()

    url = "/schedule"
    for les in lessons:
        msg = build_schedule_reminder_message(les, locale=locale)
        (
            title,
            body,
            tag,
            data_payload,
            title_translations,
            body_translations,
            dedupe_key,
        ) = msg

        key_for_dedupe = dedupe_key or tag or title
        if key_for_dedupe:
            dupe_stmt = select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user.id,
                    Notification.url == url,
                    Notification.created_at >= now - timedelta(hours=1),
                    or_(
                        Notification.dedupe_key == key_for_dedupe,
                        Notification.title == title,
                    ),
                )
            )
        else:
            dupe_stmt = select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user.id,
                    Notification.url == url,
                    Notification.created_at >= now - timedelta(hours=1),
                    Notification.title == title,
                )
            )

        res = await db.execute(dupe_stmt)
        exists = getattr(res, "scalar_one_or_none", lambda: None)()
        if exists is None:
            exists = getattr(res, "scalar_one", lambda: 0)()
        if exists:
            continue

        action_title = translate("notifications.actions.open_schedule", locale=locale)
        await create_notifications_for_users(
            db,
            title=title,
            body=body,
            title_translations=title_translations,
            body_translations=body_translations,
            type="schedule.reminder",
            url=url,
            tag=tag,
            dedupe_key=key_for_dedupe,
            payload_data=data_payload,
            actions=[
                {
                    "action": "open-schedule",
                    "title": action_title,
                    "url": url,
                }
            ],
            user_ids=[user.id],
            topic="schedule",
        )

    return await list_notifications(
        request=request,
        response=response,
        db=db,
        user=user,
        limit=20,
        cursor=None,
    )
