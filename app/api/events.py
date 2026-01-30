import hashlib
import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

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
from redis.exceptions import RedisError
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_event_service
from app.api.utils import save_upload
from app.api.validation import (
    ensure_exists,
    raise_conflict,
    raise_forbidden,
    raise_not_found,
    require_owner_or_admin,
    require_teacher_or_admin,
)
from app.core.container import get_notification_service, get_vector_service
from app.core.database import get_db
from app.core.localization import normalize_locale, resolve_locale
from app.deps.cache import RedisCache, etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.services import attendance_tokens
from app.services.event_service import EventService
from app.services.notification_service import NotificationService
from app.utils.files import delete_static_file, save_attachment

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/events", tags=["events"])

_EVENTS_LIST_CACHE_PREFIX = "events:list"
_EVENTS_LIST_VERSION_KEY = f"{_EVENTS_LIST_CACHE_PREFIX}:version"
_LOCAL_EVENTS_LIST_VERSION = 0
_EVENTS_CACHE_CONTROL = "private, max-age=180"


async def _reset_events_list_cache_version() -> None:
    global _LOCAL_EVENTS_LIST_VERSION
    _LOCAL_EVENTS_LIST_VERSION = 0
    cache = get_cache()
    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            await client.delete(_EVENTS_LIST_VERSION_KEY)
        except (RedisError, OSError):
            logger.debug("Failed to reset events cache version in Redis", exc_info=True)


async def _get_events_list_version(cache) -> str:
    if not cache.enabled:
        return str(_LOCAL_EVENTS_LIST_VERSION)
    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            raw = await client.get(_EVENTS_LIST_VERSION_KEY)
        except (RedisError, OSError):
            logger.warning(
                "Failed to read events cache version from Redis", exc_info=True
            )
            return "0"
        try:
            return str(int(raw)) if raw is not None else "0"
        except (TypeError, ValueError):
            logger.debug(
                "Invalid events cache version %s, using zero", raw, exc_info=True
            )
            return "0"
    return "0"


async def _read_events_list_version(cache) -> int:
    if not cache.enabled:
        return _LOCAL_EVENTS_LIST_VERSION
    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            raw = await client.get(_EVENTS_LIST_VERSION_KEY)
        except (RedisError, OSError):
            logger.debug(
                "Failed to read events cache version for inspection", exc_info=True
            )
            return 0
        try:
            return int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            logger.debug(
                "Invalid cached events version %s during inspection",
                raw,
                exc_info=True,
            )
            return 0
    return 0


async def _increment_events_list_version(cache) -> None:
    global _LOCAL_EVENTS_LIST_VERSION
    if not cache.enabled:
        _LOCAL_EVENTS_LIST_VERSION += 1
        return
    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            increment = getattr(client, "incr", None)
            if callable(increment):
                await increment(_EVENTS_LIST_VERSION_KEY)
            else:
                await _manual_increment_events_version(client)
        except (RedisError, OSError):
            logger.warning(
                "Failed to increment events cache version in Redis", exc_info=True
            )
        return
    _LOCAL_EVENTS_LIST_VERSION += 1


async def _manual_increment_events_version(client) -> None:
    raw = await client.get(_EVENTS_LIST_VERSION_KEY)
    try:
        current = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        current = 0
    await client.set(_EVENTS_LIST_VERSION_KEY, current + 1)


def _events_list_cache_key(
    *,
    locale: str | None,
    search: str,
    event_type: str,
    location: str,
    is_active: bool,
    limit: int,
    cursor: str | None,
    version: str,
) -> str:
    normalized_locale = normalize_locale(locale)
    normalized_search = (search or "").strip().lower()
    normalized_type = (event_type or "").strip().lower()
    normalized_location = (location or "").strip().lower()
    normalized_cursor = (cursor or "").strip()
    normalized_version = str(version or "0").strip() or "0"
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
    return (
        f"{_EVENTS_LIST_CACHE_PREFIX}:{normalized_version}:{normalized_locale}:{digest}"
    )


async def _invalidate_events_list_cache() -> None:
    cache = get_cache()
    await _increment_events_list_version(cache)


@lru_cache(maxsize=1)
def _get_vary_helper():
    from app.main import _ensure_vary_header

    return _ensure_vary_header


def _set_language_headers(response: Response, locale: str) -> None:
    response.headers["Content-Language"] = locale
    _get_vary_helper()(response, "Accept-Language")


def _encode_payload_with_etag(payload: Any) -> tuple[Any, str, str]:
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
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
    events: EventService = Depends(get_event_service),
):
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)
    try:
        record = await events.create_event(data, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await _invalidate_events_list_cache()
    await notifications.dispatch_event_created(record.id, locale, background)
    return events.serialize_event(record, locale)


@router.get(
    "",
    response_model=schemas.PaginatedEvents,
    summary="List Events",
    description="Get a paginated list of events.",
)
async def all_events(
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    search: str = Query("", alias="search"),
    type: str = Query("", alias="type"),
    location: str = Query("", alias="location"),
    is_active: bool = Query(True, alias="is_active"),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        alias="limit",
    ),
    cursor: str | None = Query(None, alias="cursor"),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_event_service),
):
    """
    Get paginated list of events.

    - **limit**: Number of items to return (1-100, default 20)
    - **cursor**: Pagination cursor for next page
    - **search**: Search query
    - **type**: Filter by event type
    - **location**: Filter by location
    - **is_active**: Filter by active status

    Returns events ordered by start date (newest first).
    """
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    response.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
    cache = get_cache()
    cache_key: str | None = None
    cache_version: str | None = None
    if cache.enabled:
        cache_version = await _get_events_list_version(cache)
        cache_key = _events_list_cache_key(
            locale=locale,
            search=search,
            event_type=type,
            location=location,
            is_active=is_active,
            limit=limit,
            cursor=cursor,
            version=cache_version,
        )
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                not_modified.headers["ETag"] = etag_header
                not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
                _set_language_headers(not_modified, locale)
                return not_modified
            response.headers["ETag"] = etag_header
            return cached.payload

    payload = await events.get_events(
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
            not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
            _set_language_headers(not_modified, locale)
            return not_modified
        response.headers["ETag"] = etag_header
        return encoded

    encoded, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
        _set_language_headers(not_modified, locale)
        return not_modified
    response.headers["ETag"] = weak_header
    return encoded


# NOTE: SQLite drops timezone information for "datetime" columns. To keep the
# comparison with ``datetime.now(timezone.utc)`` working we need to normalize
# database values back to UTC-aware timestamps before comparing them.
def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


@router.post(
    "/attendance",
    response_model=schemas.EventAttendanceOut,
    summary="Attend Event",
    description="Register attendance for an event.",
)
async def attend(
    data: schemas.EventAttendanceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
):
    """
    Register attendance for an event.

    Requires student role.
    """
    locale = resolve_locale(request=request, user=user)
    if user.role in ("admin", "teacher"):
        raise_forbidden(locale, "errors.events.registration_forbidden")
    event = await db.get(models.Event, data.event_id)
    ensure_exists(event, "events", locale)
    event_ends_at = _to_utc(event.ends_at)
    if not event.is_active or event_ends_at <= datetime.now(UTC):
        raise_conflict("errors.events.registration_closed", locale)
    try:
        return await events.register_attendance(data, user_id=user.id)
    except LookupError:
        raise_not_found("events", locale)
    except ValueError:
        raise_conflict("errors.events.registration_closed", locale)


@router.delete("/attendance", response_model=dict)
async def unregister_event(
    data: schemas.EventAttendanceCreate,
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
):
    return await events.unregister_attendance(data, user_id=user.id)


@router.get("/my", response_model=list[schemas.EventOut])
async def my_events(
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_event_service),
):
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    response.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
    payload = await events.get_my_events(user_id=user.id, locale=locale)
    encoded, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
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
    ensure_exists(event, "events", locale)
    require_owner_or_admin(user, locale, owner_id=event.created_by, allow_teacher=True)
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


@router.get("/{id}/files", response_model=list[schemas.EventFileOut])
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
):
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)
    url = await save_upload(file, "event_images", "event", locale=locale)
    return {"url": url}


@router.patch("/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: int,
    data: schemas.EventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
):
    locale = resolve_locale(request=request, user=user)
    q = await db.get(models.Event, event_id)
    ensure_exists(q, "events", locale)
    require_owner_or_admin(user, locale, owner_id=q.created_by, allow_teacher=True)
    old_image_url = q.image_url
    try:
        q = await events.update_event(event_id, data)
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
    return events.serialize_event(
        q,
        locale,
        participant_count=participant_count,
        files=files,
    )


@router.delete("/{event_id}", response_model=dict)
async def delete_event(
    event_id: int,
    request: Request,
    events: EventService = Depends(get_event_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    # Check existence and permission. Service delete checks existence, but maybe we want validation first?
    # Existing code does: ensure_exists, require_owner_or_admin.
    # We should fetch event to check logic? Or let service do it?
    # Service doesn't check owner.
    # Implementation:
    # 1. Get event (for permission check).
    # 2. Check permission.
    # 3. Call service.delete.

    # We can use service.repo.get(event_id) or just events.get_event(event_id).
    # But get_event signature: get_event(self, *, user_id=None, search...) -> Paginated.
    # No, it's list events.
    # Look for get by ID.
    # We had db.get(models.Event, event_id).

    # Let's inspect service methods again. It has repo.
    # But usage of repo in API is discouraged if we want pure service.
    # But usually we allow read.

    # For now, I'll keep db dependency just for reading event for permission check,
    # OR inject db as well.
    # BUT better refactor:
    # Use service.repo.get inside API?
    # events.repo.get(event_id).

    q = await events.repo.get(event_id)
    ensure_exists(q, "events", locale)
    require_owner_or_admin(user, locale, owner_id=q.created_by, allow_teacher=True)

    await events.delete_event(event_id)
    await _invalidate_events_list_cache()
    return {"ok": True}


@router.get("/{id}", response_model=schemas.EventOut)
async def get_event(
    id: int,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_event_service),
):
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)

    # Single query for event with files eagerly loaded
    from sqlalchemy.orm import selectinload as load_files

    result = await db.execute(
        select(models.Event)
        .where(models.Event.id == id)
        .options(load_files(models.Event.files))
    )
    q = result.scalar_one_or_none()
    ensure_exists(q, "events", locale)

    # Fetch attendance and participant count in parallel using a single query
    attendance_and_count_result = await db.execute(
        select(
            models.EventAttendance,
            (
                select(func.count())
                .select_from(models.EventAttendance)
                .where(models.EventAttendance.event_id == id)
                .correlate(None)
                .scalar_subquery()
            ).label("participant_count"),
        ).where(
            and_(
                models.EventAttendance.event_id == id,
                models.EventAttendance.user_id == user.id,
            )
        )
    )
    row = attendance_and_count_result.first()

    attendance = row[0] if row else None
    participant_count = row[1] if row else 0

    # If no attendance row, still get participant count
    if row is None:
        count_result = await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == id)
        )
        participant_count = count_result.scalar() or 0

    attendance_token: str | None = None
    if attendance:
        if attendance_tokens.ensure_secret_material(attendance):
            db.add(attendance)
            await db.commit()
            await db.refresh(attendance)
        attendance_token = attendance_tokens.issue_token(attendance)

    # Files are already loaded via selectinload
    files = getattr(q, "files", []) or []

    payload = events.serialize_event(
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
        raise_not_found("events", locale, exact_key="errors.events.file_not_found")
    event = await db.get(models.Event, ef.event_id)
    # Event is checked implicitly by permissions, but we might want to ensure it
    # still exists?
    # Assuming standard behavior, we just check permission.
    require_owner_or_admin(user, locale, owner_id=event.created_by, allow_teacher=True)
    file_url = ef.file_url
    await db.delete(ef)
    await db.commit()
    await delete_static_file(file_url)
    return {"ok": True}


@router.get("/search/semantic", response_model=list[schemas.EventOut])
async def semantic_search(
    request: Request,
    response: Response,
    query: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    vector_service: Any = Depends(get_vector_service),
    events: EventService = Depends(get_event_service),
):
    """
    Semantic search for events using embeddings.
    """
    locale = resolve_locale(request=request)
    normalized_locale = normalize_locale(locale)

    # Use ETag based on events list version
    cache = get_cache()
    version = await _get_events_list_version(cache)
    etag = format_etag(f"semantic_events:{version}:{query}:{limit}:{min_score}")
    if etag_matches(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    embedding = await vector_service.get_embedding(query)
    results = await vector_service.search_similar(
        models.Event, embedding, limit=limit, min_score=min_score
    )

    items = [events.serialize_event(item, locale) for item in results]
    response.headers["ETag"] = etag
    _set_language_headers(response, normalized_locale)
    return items


__all__ = ["router"]
