from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from functools import lru_cache
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.localization import resolve_locale, translate, translate_lesson_type
from app.models import models
from app.schemas import schemas


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


def _localize_schedule_payload(
    payload: Sequence[Mapping[str, Any]] | Sequence[Any], *, locale: str | None
) -> list[dict[str, Any]]:
    localized: list[dict[str, Any]] = []
    for item in payload:
        data = dict(item)
        raw_type = data.get("lesson_type")
        display = translate_lesson_type(raw_type, locale=locale)
        data["lesson_type_display"] = display
        localized.append(data)
    return localized


@router.post("", response_model=schemas.ScheduleOut)
async def add_schedule(
    data: schemas.ScheduleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    result = await crud.create_schedule(db, data)
    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(result.group_id))
    return result


@router.get("/{group_id}", response_model=list[schemas.ScheduleOut])
async def get_schedule(
    group_id: int,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    _get_vary_helper()(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    _set_schedule_cache_headers(response)
    cache = get_cache()
    cache_key = _schedule_cache_key(group_id)
    if cache.enabled:
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                cached_response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                cached_response.headers["ETag"] = etag_header
                _get_vary_helper()(cached_response, "Accept-Language")
                _set_schedule_cache_headers(cached_response)
                return cached_response
            response.headers["ETag"] = etag_header
            return _localize_schedule_payload(cached.payload, locale=locale)

    rows = await crud.get_schedule_by_group(db, group_id)
    models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)
    localized_payload = _localize_schedule_payload(payload, locale=locale)

    if cache.enabled:
        entry = await cache.set(cache_key, payload, ttl=_SCHEDULE_CACHE_TTL_SECONDS)
        response.headers["ETag"] = format_etag(entry.etag)
    return localized_payload


@router.patch("/{schedule_id}", response_model=schemas.ScheduleOut)
async def update_schedule(
    schedule_id: int,
    data: schemas.ScheduleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.schedule.not_found", locale=locale),
        )
    previous_group = sched.group_id
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sched, field, value)
    await db.commit()
    await db.refresh(sched)
    cache = get_cache()
    await cache.invalidate(
        _schedule_cache_key(previous_group),
        _schedule_cache_key(sched.group_id),
    )
    return sched


@router.delete("/{schedule_id}", response_model=dict)
async def delete_schedule(
    schedule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.schedule.not_found", locale=locale),
        )
    group_id = sched.group_id
    await db.delete(sched)
    await db.commit()
    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(group_id))
    return {"ok": True}


__all__ = ["router"]
