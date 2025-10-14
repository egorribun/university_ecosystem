from typing import List

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
from app.localization import resolve_locale, translate
from app.models import models
from app.schemas import schemas

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _schedule_cache_key(group_id: int) -> str:
    return f"schedule:group:{group_id}"


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


@router.get("/{group_id}", response_model=List[schemas.ScheduleOut])
async def get_schedule(
    group_id: int,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    cache = get_cache()
    cache_key = _schedule_cache_key(group_id)
    if cache.enabled:
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload

    rows = await crud.get_schedule_by_group(db, group_id)
    models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)

    if cache.enabled:
        entry = await cache.set(cache_key, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


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
