from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from functools import lru_cache

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Response,
    status,
)

from app.api.deps import get_current_user, get_schedule_service
from app.api.validation import ensure_exists, require_teacher_or_admin
from app.core.container import get_schedule_handler
from app.core.localization import resolve_locale
from app.cqrs.queries import GetScheduleHandler, GetScheduleQuery
from app.deps.cache import get_cache
from app.models import models
from app.schemas import schemas
from app.services.schedule_service import ScheduleService


@lru_cache(maxsize=1)
def _get_vary_helper() -> Callable[[Response, str], None]:
    from app.main import _ensure_vary_header

    return _ensure_vary_header


_SCHEDULE_CACHE_TTL_SECONDS = 300
_SCHEDULE_CACHE_CONTROL = f"private, max-age={_SCHEDULE_CACHE_TTL_SECONDS}"


router = APIRouter(prefix="/schedule", tags=["schedule"])


def _schedule_cache_key(group_id: int) -> str:
    return f"schedule:group:{group_id}"


def _set_schedule_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = _SCHEDULE_CACHE_CONTROL
    expires_at = datetime.now(UTC) + timedelta(seconds=_SCHEDULE_CACHE_TTL_SECONDS)
    response.headers["Expires"] = format_datetime(expires_at, usegmt=True)


@router.post("", response_model=schemas.ScheduleOut)
async def add_schedule(
    data: schemas.ScheduleCreate,
    request: Request,
    service: ScheduleService = Depends(get_schedule_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    from app.api.validation import raise_conflict
    from app.core.exceptions.domain import BusinessRuleViolation

    try:
        result = await service.create_schedule(data, locale=locale)
    except BusinessRuleViolation as e:
        # Map domain exception to API conflict error
        raise_conflict(str(e), locale, exact_key="errors.schedule.conflict")

    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(result.group_id))
    return result


@router.get("/{group_id}", response_model=list[schemas.ScheduleOut])
async def get_schedule(
    group_id: int,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    handler: GetScheduleHandler = Depends(get_schedule_handler),
):
    locale = resolve_locale(request=request)
    _get_vary_helper()(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    _set_schedule_cache_headers(response)

    query = GetScheduleQuery(
        group_id=group_id, locale=locale, if_none_match=if_none_match
    )
    result = await handler.handle(query)

    if result.not_modified:
        cached_response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        cached_response.headers["ETag"] = result.etag
        _get_vary_helper()(cached_response, "Accept-Language")
        _set_schedule_cache_headers(cached_response)
        return cached_response

    if result.etag:
        response.headers["ETag"] = result.etag

    return result.payload


@router.patch("/{schedule_id}", response_model=schemas.ScheduleOut)
async def update_schedule(
    schedule_id: int,
    data: schemas.ScheduleUpdate,
    request: Request,
    service: ScheduleService = Depends(get_schedule_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    # We need previous group ID for cache invalidation
    sched = await service.get_by_id(schedule_id)
    ensure_exists(sched, "schedule", locale)
    previous_group = sched.group_id

    try:
        updated = await service.update_schedule(schedule_id, data)
    except ValueError:
        ensure_exists(None, "schedule", locale)  # Will raise 404

    cache = get_cache()
    await cache.invalidate(
        _schedule_cache_key(previous_group),
        _schedule_cache_key(updated.group_id),
    )
    return updated


@router.delete("/{schedule_id}", response_model=dict)
async def delete_schedule(
    schedule_id: int,
    request: Request,
    service: ScheduleService = Depends(get_schedule_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    sched = await service.get_by_id(schedule_id)
    ensure_exists(sched, "schedule", locale)
    group_id = sched.group_id

    deleted = await service.delete_schedule(schedule_id)
    if not deleted:
        ensure_exists(None, "schedule", locale)

    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(group_id))
    return {"ok": True}


__all__ = ["router"]
