from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.core.database import get_db
from app.deps.cache import get_cache
from app.localization import resolve_locale, translate
from app.models import models

router = APIRouter(prefix="/stats", tags=["stats"])


_PERIOD_ALIASES = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
}

_PERIOD_DEFAULT = ("30d", 30)


def _resolve_period(period: str | None) -> tuple[str, int]:
    if not period:
        return _PERIOD_DEFAULT
    period_key = period.strip().lower()
    days = _PERIOD_ALIASES.get(period_key)
    if days is not None:
        return period_key, days
    return _PERIOD_DEFAULT


def _should_skip_cache(requested: bool, user: models.User) -> bool:
    if not requested:
        return False
    return user.role == "admin"


def _period_response_payload(
    *,
    stats: dict[str, object],
    period_key: str,
    period_days: int,
    request: Request,
    user: models.User,
) -> dict[str, object]:
    locale = resolve_locale(request=request, user=user)
    label = translate(
        f"stats.period.{period_key}",
        locale=locale,
        default=period_key,
        days=period_days,
    )
    payload = dict(stats)
    payload["period_key"] = stats.get("period_key") or period_key
    payload["period_label"] = label
    return payload


@router.get("/attendance")
async def attendance_summary(
    request: Request,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    cache_backend = get_cache()
    stats = await crud.get_attendance_stats(
        db,
        user_id=user.id,
        period_days=days,
        period_key=period_key,
        cache=cache_backend,
        skip_cache=_should_skip_cache(skip_cache, user),
    )
    return _period_response_payload(
        stats=stats,
        period_key=period_key,
        period_days=days,
        request=request,
        user=user,
    )


@router.get("/grades")
async def grade_summary(
    request: Request,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    cache_backend = get_cache()
    stats = await crud.get_grade_stats(
        db,
        user_id=user.id,
        period_days=days,
        cache=cache_backend,
        period_key=period_key,
        skip_cache=_should_skip_cache(skip_cache, user),
    )
    return _period_response_payload(
        stats=stats,
        period_key=period_key,
        period_days=days,
        request=request,
        user=user,
    )


@router.get("/participation")
async def participation_summary(
    request: Request,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    cache_backend = get_cache()
    stats = await crud.get_participation_stats(
        db,
        user_id=user.id,
        period_days=days,
        cache=cache_backend,
        period_key=period_key,
        skip_cache=_should_skip_cache(skip_cache, user),
    )
    return _period_response_payload(
        stats=stats,
        period_key=period_key,
        period_days=days,
        request=request,
        user=user,
    )
