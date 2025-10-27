import hashlib
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, List, Tuple

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.localization import normalize_locale, resolve_locale, translate
from app.models import models
from app.schemas import schemas
from app.services import attendance_tokens, notification_queue
from app.utils.files import delete_static_file, save_attachment

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/events", tags=["events"])

_EVENTS_LIST_CACHE_PREFIX = "events:list"
_events_list_cache_keys: set[str] = set()


def _register_events_cache_key(key: str) -> None:
    if key:
        _events_list_cache_keys.add(key)


def _consume_events_cache_keys() -> list[str]:
    if not _events_list_cache_keys:
        return []
    keys = list(_events_list_cache_keys)
    _events_list_cache_keys.clear()
    return keys


def _events_cache_keys_snapshot() -> tuple[str, ...]:
    return tuple(sorted(_events_list_cache_keys))


def _reset_events_cache_registry() -> None:
    _events_list_cache_keys.clear()


def _events_list_cache_key(
    *,
    locale: str | None,
    search: str,
    event_type: str,
    location: str,
    is_active: bool,
    limit: int,
    cursor: str | None,
) -> str:
    normalized_locale = normalize_locale(locale)
    normalized_search = (search or "").strip().lower()
    normalized_type = (event_type or "").strip().lower()
    normalized_location = (location or "").strip().lower()
    normalized_cursor = (cursor or "").strip()
    signature = json.dumps(
        {
            "search": normalized_search,
            "type": normalized_type,
            "location": normalized_location,
            "is_active": bool(is_active),
            "limit": int(limit),
            "cursor": normalized_cursor,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(signature).hexdigest()
    return f"{_EVENTS_LIST_CACHE_PREFIX}:{normalized_locale}:{digest}"


async def _invalidate_events_list_cache() -> None:
    keys = _consume_events_cache_keys()
    if not keys:
        return
    cache = get_cache()
    if cache.enabled:
        await cache.invalidate(*keys)


@lru_cache(maxsize=1)
def _get_vary_helper():
    from app.main import _ensure_vary_header

    return _ensure_vary_header


def _set_language_headers(response: Response, locale: str) -> None:
    response.headers["Content-Language"] = locale
    _get_vary_helper()(response, "Accept-Language")


def _encode_payload_with_etag(payload: Any) -> Tuple[Any, str, str]:
    encoded = jsonable_encoder(payload)
    serialized = json.dumps(
        encoded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    weak_header = f"W/{format_etag(digest)}"
    return encoded, digest, weak_header


@router.post("", response_model=schemas.EventOut)
async def create_event(
    data: schemas.EventCreate,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    record = await crud.create_event(db, data, user_id=user.id)
    await _invalidate_events_list_cache()
    try:
        background.add_task(
            notification_queue.enqueue_event_notification,
            record.id,
            locale=locale,
        )
    except Exception:
        logger.exception(
            "Failed to enqueue event notification", extra={"event_id": record.id}
        )
    return crud.serialize_event(record, locale)


@router.get("", response_model=schemas.PaginatedEvents)
async def all_events(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    search: str = Query("", alias="search"),
    type: str = Query("", alias="type"),
    location: str = Query("", alias="location"),
    is_active: bool = Query(True, alias="is_active"),
    limit: int = Query(
        crud.DEFAULT_EVENTS_LIMIT,
        ge=1,
        le=crud.MAX_EVENTS_LIMIT,
        alias="limit",
    ),
    cursor: str | None = Query(None, alias="cursor"),
    if_none_match: str | None = Header(default=None),
):
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    cache = get_cache()
    cache_key: str | None = None
    if cache.enabled:
        cache_key = _events_list_cache_key(
            locale=locale,
            search=search,
            event_type=type,
            location=location,
            is_active=is_active,
            limit=limit,
            cursor=cursor,
        )
        _register_events_cache_key(cache_key)
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                not_modified.headers["ETag"] = etag_header
                _set_language_headers(not_modified, locale)
                return not_modified
            response.headers["ETag"] = etag_header
            return cached.payload

    payload = await crud.get_all_events(
        db,
        user_id=user.id,
        search=search,
        type=type,
        location=location,
        is_active=is_active,
        locale=locale,
        limit=limit,
        cursor=cursor,
    )

    encoded = jsonable_encoder(payload)

    if cache.enabled and cache_key:
        entry = await cache.set(cache_key, encoded)
        etag_header = format_etag(entry.etag)
        if etag_matches(entry.etag, if_none_match):
            not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
            not_modified.headers["ETag"] = etag_header
            _set_language_headers(not_modified, locale)
            return not_modified
        response.headers["ETag"] = etag_header
        return encoded

    encoded, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        _set_language_headers(not_modified, locale)
        return not_modified
    response.headers["ETag"] = weak_header
    return encoded


# NOTE: SQLite drops timezone information for "datetime" columns. To keep the
# comparison with ``datetime.now(timezone.utc)`` working we need to normalize
# database values back to UTC-aware timestamps before comparing them.
def _to_utc(dt: datetime) -> datetime:
    return (
        dt.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None
        else dt.astimezone(timezone.utc)
    )


@router.post("/attendance", response_model=schemas.EventAttendanceOut)
async def attend(
    data: schemas.EventAttendanceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role in ("admin", "teacher"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.events.registration_forbidden", locale=locale),
        )
    event = await db.get(models.Event, data.event_id)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        )
    event_ends_at = _to_utc(event.ends_at)
    if not event.is_active or event_ends_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=translate("errors.events.registration_closed", locale=locale),
        )
    try:
        return await crud.register_attendance(db, data, user_id=user.id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=translate("errors.events.registration_closed", locale=locale),
        ) from exc


@router.delete("/attendance", response_model=dict)
async def unregister_event(
    data: schemas.EventAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return await crud.unregister_attendance(db, data, user_id=user.id)


@router.get("/my", response_model=List[schemas.EventOut])
async def my_events(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
):
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    payload = await crud.get_my_events(db, user_id=user.id, locale=locale)
    encoded, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        _set_language_headers(not_modified, locale)
        return not_modified
    response.headers["ETag"] = weak_header
    return encoded


@router.post("/{id}/upload_file", response_model=schemas.EventFileOut)
async def upload_event_file(
    id: int,
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    event = await db.get(models.Event, id)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        )
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    url = await save_attachment(file, "event_files", f"event_{id}", locale=locale)
    ef = models.EventFile(event_id=id, file_url=url)
    db.add(ef)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await delete_static_file(url)
        raise
    try:
        await db.refresh(ef)
    except Exception:
        await delete_static_file(url)
        raise
    return ef


@router.get("/{id}/files", response_model=List[schemas.EventFileOut])
async def get_event_files(id: int, db: AsyncSession = Depends(get_db)):
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == id)
            )
        )
        .scalars()
        .all()
    )
    return files


@router.post("/upload_image")
async def upload_event_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request, user=user)
    if user.role not in ("admin", "teacher"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    url = await save_upload(file, "event_images", "event", locale=locale)
    return {"url": url}


@router.patch("/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: int,
    data: schemas.EventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        )
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    old_image_url = q.image_url
    try:
        q = await crud.update_event(db, q, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if old_image_url and q.image_url != old_image_url:
        await delete_static_file(old_image_url)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    await _invalidate_events_list_cache()
    return crud.serialize_event(
        q,
        locale,
        participant_count=participant_count,
        files=files,
    )


@router.delete("/{event_id}", response_model=dict)
async def delete_event(
    event_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        )
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    event_image_url = q.image_url
    file_urls = [
        row[0]
        for row in (
            await db.execute(
                select(models.EventFile.file_url).where(
                    models.EventFile.event_id == event_id
                )
            )
        ).all()
        if row[0]
    ]
    await db.execute(
        delete(models.EventFile).where(models.EventFile.event_id == event_id)
    )
    await db.delete(q)
    await db.commit()
    await _invalidate_events_list_cache()
    if event_image_url:
        await delete_static_file(event_image_url)
    for url in file_urls:
        await delete_static_file(url)
    return {"ok": True}


@router.get("/{id}", response_model=schemas.EventOut)
async def get_event(
    id: int,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
):
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    q = await db.get(models.Event, id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.not_found", locale=locale),
        )
    attendance = (
        await db.execute(
            select(models.EventAttendance).where(
                and_(
                    models.EventAttendance.event_id == q.id,
                    models.EventAttendance.user_id == user.id,
                )
            )
        )
    ).scalar_one_or_none()
    attendance_token: str | None = None
    if attendance:
        if attendance_tokens.ensure_secret_material(attendance):
            db.add(attendance)
            await db.commit()
            await db.refresh(attendance)
        attendance_token = attendance_tokens.issue_token(attendance)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    payload = crud.serialize_event(
        q,
        locale,
        participant_count=participant_count,
        files=files,
        is_registered=attendance is not None,
        my_qr_token=attendance_token,
    )
    encoded, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        _set_language_headers(not_modified, locale)
        return not_modified
    response.headers["ETag"] = weak_header
    return encoded


@router.delete("/file/{file_id}", response_model=dict)
async def delete_event_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    ef = await db.get(models.EventFile, file_id)
    if not ef:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.events.file_not_found", locale=locale),
        )
    event = await db.get(models.Event, ef.event_id)
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    file_url = ef.file_url
    await db.delete(ef)
    await db.commit()
    await delete_static_file(file_url)
    return {"ok": True}


__all__ = ["router"]
