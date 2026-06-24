import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.api.deps import (
    get_current_user,
    get_event_service,
    get_read_event_service,
)
from app.api.deps.auth import get_permission_checker
from app.api.deps.etag import _set_language_headers, cached_endpoint
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
from app.core.logging import get_logger
from app.core.ratelimit import sensitive_route_limit
from app.deps.cache import etag_matches, format_etag, get_cache
from app.schemas import schemas
from app.schemas.dtos import EventFileDTO
from app.services.event_service import EventService
from app.services.file_scanner import scan_for_malware
from app.services.notification_service import NotificationService
from app.utils.files import delete_static_file, save_attachment

logger = get_logger(__name__)


router = APIRouter(prefix="/events", tags=["events"])

_EVENTS_CACHE_CONTROL = "private, max-age=180"


def _validate_id_type(id_val: uuid.UUID | int) -> None:
    if isinstance(id_val, int):
        # Prevent SQLite/Postgres 64-bit signed integer overflow
        if not (-9223372036854775808 <= id_val <= 9223372036854775807):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID out of 64-bit integer range."
            )

_EVENTS_LIST_CACHE_PREFIX = events_cache_version.prefix


async def _get_events_list_version(cache: Any) -> str:
    return await events_cache_version.get_version(cache)


async def _increment_events_list_version(cache: Any | None) -> None:
    if cache is not None:
        await events_cache_version.increment(cache)


# Removed obsolete cache key extraction and serialization helpers (now in deps/etag.py)


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
        # TD-W19-01 (audit 2026-03-24 Wave 19): use localized error key instead of
        # raw exception message. Previously str(exc) leaked internal error details.
        logger.warning("Event creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="errors.events.creation_failed",
        ) from exc
    if request:
        await _increment_events_list_version(getattr(request.app.state, "cache", None))
    await notifications.dispatch_event_created(record.id, locale, background)
    return events.serialize_event(record, locale)


@router.get(
    "",
    response_model=schemas.PaginatedEvents,
    summary="List Events",
    description="Get a paginated list of events.",
)
@cached_endpoint(
    version_resolver=events_cache_version,
    cache_prefix=_EVENTS_LIST_CACHE_PREFIX,
    cache_control=_EVENTS_CACHE_CONTROL,
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

    # TD-01 & PERF-02 (audit 2026-03): Delegated all ETag formatting, 304 Not Modified
    # logic, Redis version checking, and serialization to `deps.etag.cached_endpoint`.
    # This keeps the router focused strictly on business logic and routing.
    return payload


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
    assert event is not None  # noqa: S101
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
@cached_endpoint(
    version_resolver=events_cache_version,
    cache_prefix="ue:events:my",
    cache_control=_EVENTS_CACHE_CONTROL,
)
async def my_events(
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_read_event_service),
) -> list[schemas.EventOut] | Response | Any:
    locale = resolve_locale(request=request, user=user)
    payload = await events.get_my_events(user_id=user.id, locale=locale)
    return payload


@router.post(
    "/{event_id}/upload_file",
    response_model=schemas.EventFileOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_upload))
    ],
)
async def upload_event_file(
    event_id: uuid.UUID | int,
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    checker: PermissionChecker = Depends(get_permission_checker),
) -> models.EventFile:
    _validate_id_type(event_id)
    locale = resolve_locale(request=request, user=user)
    event = await db.get(models.Event, event_id)
    ensure_exists(event, "events", locale)
    assert event is not None  # noqa: S101
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event.id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)
    await scan_for_malware(file, locale=locale, size_bytes=file.size)
    url = await save_attachment(file, "event_files", f"event_{event_id}", locale=locale)
    ef = models.EventFile(event_id=event_id, file_url=url)
    db.add(ef)
    try:
        await db.commit()
    except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback and cleanup file then re-raise (reviewed TD-27-04)
        await db.rollback()
        await delete_static_file(str(url))
        raise
    try:
        await db.refresh(ef)
    except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — cleanup file then re-raise (reviewed TD-27-04)
        await delete_static_file(str(url))
        raise
    return ef


@router.get("/{event_id}/files", response_model=list[schemas.EventFileOut])
async def get_event_files(
    event_id: uuid.UUID | int, db: AsyncSession = Depends(get_read_db)
) -> list[models.EventFile]:
    _validate_id_type(event_id)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == event_id)
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
    event_id: uuid.UUID | int = Form(...),
    db: AsyncSession = Depends(get_db),
    checker: PermissionChecker = Depends(get_permission_checker),
) -> dict[str, str]:
    _validate_id_type(event_id)
    locale = resolve_locale(request=request, user=user)

    # RZ-003 Fix: Deny unlinked anonymous file uploads to prevent Storage DoS
    event = await db.get(models.Event, event_id)
    ensure_exists(event, "events", locale)
    assert event is not None  # noqa: S101

    # Check if user has edit rights for this specific event
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event.id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)

    await scan_for_malware(file, locale=locale, size_bytes=file.size)

    from contextlib import suppress

    from app.utils.files import delete_static_file

    url = ""
    try:
        # RZ-003: Upload to 'tmp/' prefix. A MinIO lifecycle policy will reap
        # objects in this prefix that are older than 24h, mitigating storage DoS
        # from abandoned uploads. A separate worker or client action must copy
        # the file to permanent storage when the event is actually saved.
        url = await save_upload(
            file, "tmp/event_images", f"event_{event_id}", locale=locale
        )
        return {"url": url}
    except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — cleanup uploaded file then re-raise (reviewed TD-27-04)
        if url:
            with suppress(Exception):
                await delete_static_file(str(url))
        raise


@router.patch("/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: uuid.UUID | int,
    data: schemas.EventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    events: EventService = Depends(get_event_service),
    checker: PermissionChecker = Depends(get_permission_checker),
) -> schemas.EventOut:
    locale = resolve_locale(request=request, user=user)
    q = await db.get(models.Event, event_id)
    ensure_exists(q, "events", locale)
    assert q is not None  # noqa: S101

    # ReBAC: Migrated from require_owner_or_admin
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event_id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)

    old_image_url = q.image_url
    if isinstance(event_id, int):
        raise HTTPException(
            status_code=400,
            detail="Integer event IDs are not supported; use a UUID.",
        )
    ev_id = event_id
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

    if request:
        await _increment_events_list_version(getattr(request.app.state, "cache", None))
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
    checker: PermissionChecker = Depends(get_permission_checker),
) -> dict[str, bool]:
    _validate_id_type(event_id)
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
    if request:
        await _increment_events_list_version(getattr(request.app.state, "cache", None))
    return {"ok": True}


@router.get("/{event_id}", response_model=schemas.EventOut)
@cached_endpoint(
    version_resolver=events_cache_version,
    cache_prefix="ue:events:detail",
    cache_control=_EVENTS_CACHE_CONTROL,
)
async def get_event(
    event_id: uuid.UUID | int,
    request: Request,
    response: Response,
    user: models.User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
    events: EventService = Depends(get_read_event_service),
) -> schemas.EventOut | Response | Any:
    _validate_id_type(event_id)
    locale = resolve_locale(request=request, user=user)

    payload = await events.get_event_detail(event_id, user.id, locale=locale)
    if not payload:
        raise_not_found("events", locale)

    return payload


@router.delete("/file/{file_id}", response_model=dict)
async def delete_event_file(
    file_id: uuid.UUID | int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    checker: PermissionChecker = Depends(get_permission_checker),
) -> dict[str, bool]:
    _validate_id_type(file_id)
    locale = resolve_locale(request=request, user=user)
    ef = await db.get(models.EventFile, file_id)
    if not ef:
        raise_not_found("events", locale, exact_key="errors.events.file_not_found")
    assert ef is not None  # noqa: S101  # narrowing for type checkers
    event = await db.get(models.Event, ef.event_id)
    # RZ-004 (audit 2026-03-04): explicitly guard against a concurrently deleted
    # parent event. Without this check `event.created_by` raises AttributeError
    # which propagated as an unhandled 500, while the file deletion still
    # proceeded — an authorization bypass.
    ensure_exists(event, "events", locale)
    assert event is not None  # noqa: S101  # narrowing for type checkers
    if not await checker.check_permission(
        resource_type="event",
        resource_id=str(event.id),
        permission="edit",
        user_id=str(user.id),
    ):
        raise_forbidden(locale)
    file_url = ef.file_url
    # RZ-003 Fix: Delete from storage BEFORE committing the DB transaction.
    # This prevents orphaned files in storage if the DB commit fails or is
    # interrupted. While this may leave a "broken link" in the DB if the
    # storage deletion succeeds but commit fails, it prevents the more
    # dangerous "Storage Exhaustion DoS" vector where unlinked files
    # accumulate indefinitely without any path for automated cleanup.
    await delete_static_file(str(file_url))
    await db.delete(ef)
    await db.commit()
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
    _user: models.User = Depends(get_current_user),  # P0-W5-01: auth gate
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
