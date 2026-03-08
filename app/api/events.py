import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, cast

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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_event_service,
    get_read_event_service,
)
from app.api.utils import save_upload
from app.api.validation import (
    ensure_exists,
    raise_conflict,
    raise_forbidden,
    raise_not_found,
    require_teacher_or_admin,
)
from app.auth.rbac import PermissionChecker
from app.core.cache_versioning import events_cache_version
from app.core.config import settings
from app.core.container import get_notification_service, get_vector_service
from app.core.database import get_db, get_read_db
from app.core.localization import normalize_locale, resolve_locale
from app.core.ratelimit import sensitive_route_limit
from app.deps.cache import etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.schemas.dtos import EventFileDTO
from app.services.event_service import EventService
from app.services.file_scanner import scan_for_malware
from app.services.notification_service import NotificationService
from app.utils.files import delete_static_file, save_attachment

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/events", tags=["events"])

_EVENTS_CACHE_CONTROL = "private, max-age=180"
_EVENTS_LIST_CACHE_PREFIX = events_cache_version.prefix


async def _get_events_list_version(cache: Any) -> str:
    return await events_cache_version.get_version(cache)


async def _increment_events_list_version(cache: Any) -> None:
    await events_cache_version.increment(cache)


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
def _get_vary_helper() -> Any:
    from app.main import _ensure_vary_header

    return _ensure_vary_header


def _set_language_headers(response: Response, locale: str) -> None:
    response.headers["Content-Language"] = locale
    _get_vary_helper()(response, "Accept-Language")


def _encode_payload_with_etag(payload: Any) -> tuple[Response, str, str]:
    encoded = jsonable_encoder(payload)

    # PERF-1 Optimization: Use rapid JSON serialization and return Response directly
    # to avoid a secondary automatic FastAPI serialization later in the pipeline
    import orjson

    serialized_bytes = orjson.dumps(encoded, option=orjson.OPT_SORT_KEYS)
    digest = hashlib.sha256(serialized_bytes).hexdigest()

    strong_header = f'"{format_etag(digest).strip(chr(34))}"'

    return (
        Response(content=serialized_bytes, media_type="application/json"),
        digest,
        strong_header,
    )


@router.post(
    "",
    response_model=schemas.EventOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_events))
    ],
)
async def create_event(
    data: schemas.EventCreate,
    request: Request,
    background: BackgroundTasks,
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
    events: EventService = Depends(get_event_service),
) -> schemas.EventOut:
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
    events: EventService = Depends(get_read_event_service),
) -> schemas.PaginatedEvents | Response | dict[str, Any]:
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
            return cast(dict[str, Any], cached.payload)

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
        return cast(dict[str, Any], encoded)

    encoded_response, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
        _set_language_headers(not_modified, locale)
        return not_modified

    encoded_response.headers["ETag"] = weak_header
    encoded_response.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
    _set_language_headers(encoded_response, locale)
    return encoded_response


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
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_interactions))
    ],
)
async def attend(
    data: schemas.EventAttendanceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
) -> schemas.EventAttendanceOut:
    """
    Register attendance for an event.

    Requires student role.
    """
    locale = resolve_locale(request=request, user=user)
    if user.role in ("admin", "teacher"):
        raise_forbidden(locale, "errors.events.registration_forbidden")
    event = await db.get(models.Event, data.event_id)
    ensure_exists(event, "events", locale)
    assert event is not None  # nosec B101
    event_ends_at = _to_utc(event.ends_at)
    if not event.is_active or event_ends_at <= datetime.now(UTC):
        raise_conflict("errors.events.registration_closed", locale)
    try:
        dto = await events.register_attendance(data, user_id=user.id)
        return schemas.EventAttendanceOut.model_validate(dto)
    except LookupError:
        raise_not_found("events", locale)
    except ValueError:
        raise_conflict("errors.events.registration_closed", locale)


@router.delete("/attendance", response_model=dict)
async def unregister_event(
    data: schemas.EventAttendanceCreate,
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
) -> dict[str, bool]:
    return await events.unregister_attendance(data, user_id=user.id)


@router.get("/my", response_model=list[schemas.EventOut])
async def my_events(
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_read_event_service),
) -> list[schemas.EventOut] | Response | Any:
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)
    response.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
    payload = await events.get_my_events(user_id=user.id, locale=locale)
    encoded_response, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        not_modified.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
        _set_language_headers(not_modified, locale)
        return not_modified

    encoded_response.headers["ETag"] = weak_header
    encoded_response.headers["Cache-Control"] = _EVENTS_CACHE_CONTROL
    _set_language_headers(encoded_response, locale)
    return encoded_response


@router.post(
    "/{id}/upload_file",
    response_model=schemas.EventFileOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_upload))
    ],
)
async def upload_event_file(
    id: uuid.UUID | int,
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    checker: PermissionChecker = Depends(),
) -> models.EventFile:
    locale = resolve_locale(request=request, user=user)
    event = await db.get(models.Event, id)
    ensure_exists(event, "events", locale)
    assert event is not None  # nosec B101
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event.id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)
    await scan_for_malware(file, locale=locale, size_bytes=file.size)
    url = await save_attachment(file, "event_files", f"event_{id}", locale=locale)
    ef = models.EventFile(event_id=id, file_url=url)
    db.add(ef)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await delete_static_file(str(url))
        raise
    try:
        await db.refresh(ef)
    except Exception:
        await delete_static_file(str(url))
        raise
    return ef


@router.get("/{id}/files", response_model=list[schemas.EventFileOut])
async def get_event_files(
    id: uuid.UUID | int, db: AsyncSession = Depends(get_read_db)
) -> list[models.EventFile]:
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == id)
            )
        )
        .scalars()
        .all()
    )
    return list(files)


@router.post(
    "/upload_image",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_upload))
    ],
)
async def upload_event_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
) -> dict[str, str]:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)
    await scan_for_malware(file, locale=locale, size_bytes=file.size)
    url = await save_upload(file, "event_images", "event", locale=locale)
    return {"url": url}


@router.patch("/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: uuid.UUID | int,
    data: schemas.EventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
    checker: PermissionChecker = Depends(),
) -> schemas.EventOut:
    locale = resolve_locale(request=request, user=user)
    q = await db.get(models.Event, event_id)
    ensure_exists(q, "events", locale)
    assert q is not None  # nosec B101

    # ReBAC: Migrated from require_owner_or_admin
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event_id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)

    old_image_url = q.image_url
    ev_id = uuid.UUID(str(event_id)) if isinstance(event_id, int) else event_id
    try:
        event_dto = await events.update_event(ev_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if old_image_url and event_dto.image_url != old_image_url:
        await delete_static_file(str(old_image_url))

    files_result = await db.execute(
        select(models.EventFile).where(models.EventFile.event_id == event_dto.id)
    )
    files = [EventFileDTO.model_validate(f) for f in files_result.scalars().all()]

    participant_count_res = await db.execute(
        select(func.count())
        .select_from(models.EventAttendance)
        .where(models.EventAttendance.event_id == event_dto.id)
    )
    participant_count = participant_count_res.scalar() or 0

    await _invalidate_events_list_cache()
    return events.serialize_event(
        event_dto,
        locale,
        participant_count=int(participant_count),
        files=files,
    )


@router.delete("/{event_id}", response_model=dict)
async def delete_event(
    event_id: uuid.UUID | int,
    request: Request,
    events: EventService = Depends(get_event_service),
    user: models.User = Depends(get_current_user),
    checker: PermissionChecker = Depends(),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)

    # RZ-003 (audit 2026-03-04): Replaced require_owner_or_admin() with
    # SpiceDB ReBAC check to stay consistent with update_event. Users whose
    # editor permission was revoked via SpiceDB could previously still delete
    # events via the legacy RBAC path because they remained the DB owner.
    q = await events.get_event_by_id(event_id)
    ensure_exists(q, "events", locale)

    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event_id),
        permission="delete",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)

    await events.delete_event(event_id)
    await _invalidate_events_list_cache()
    return {"ok": True}


@router.get("/{id}", response_model=schemas.EventOut)
async def get_event(
    id: uuid.UUID | int,
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_read_event_service),
) -> schemas.EventOut | Response | Any:
    locale = resolve_locale(request=request, user=user)
    _set_language_headers(response, locale)

    payload = await events.get_event_detail(id, user.id, locale=locale)
    if not payload:
        raise_not_found("events", locale)

    encoded_response, digest, weak_header = _encode_payload_with_etag(payload)
    if etag_matches(digest, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        not_modified.headers["ETag"] = weak_header
        _set_language_headers(not_modified, locale)
        return not_modified

    encoded_response.headers["ETag"] = weak_header
    _set_language_headers(encoded_response, locale)
    return encoded_response


@router.delete("/file/{file_id}", response_model=dict)
async def delete_event_file(
    file_id: uuid.UUID | int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    checker: PermissionChecker = Depends(),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    ef = await db.get(models.EventFile, file_id)
    if not ef:
        raise_not_found("events", locale, exact_key="errors.events.file_not_found")
    assert ef is not None  # nosec B101 # narrowing for type checkers
    event = await db.get(models.Event, ef.event_id)
    # RZ-004 (audit 2026-03-04): explicitly guard against a concurrently deleted
    # parent event. Without this check `event.created_by` raises AttributeError
    # which propagated as an unhandled 500, while the file deletion still
    # proceeded — an authorization bypass.
    ensure_exists(event, "events", locale)
    assert event is not None  # nosec B101 # narrowing for type checkers
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event.id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)
    file_url = ef.file_url
    await db.delete(ef)
    await db.commit()
    await delete_static_file(str(file_url))
    return {"ok": True}


@router.get(
    "/search/semantic",
    response_model=list[schemas.EventOut],
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_graphql))
    ],
)
async def semantic_search(
    request: Request,
    response: Response,
    query: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_read_db),
    vector_service: Any = Depends(get_vector_service),
    events: EventService = Depends(get_read_event_service),
) -> list[schemas.EventOut] | Response:
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
