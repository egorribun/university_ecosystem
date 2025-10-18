from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import models

router = APIRouter(prefix="/stats", tags=["stats"])


_PERIOD_ALIASES = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
}


def _resolve_period(period: str | None) -> int:
    if not period:
        return 30
    period_key = period.strip().lower()
    return _PERIOD_ALIASES.get(period_key, 30)


@router.get("/attendance")
async def attendance_summary(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    days = _resolve_period(period)
    return await crud.get_attendance_stats(db, user_id=user.id, period_days=days)


@router.get("/grades")
async def grade_summary(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    days = _resolve_period(period)
    return await crud.get_grade_stats(db, user_id=user.id, period_days=days)


@router.get("/participation")
async def participation_summary(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    days = _resolve_period(period)
    return await crud.get_participation_stats(db, user_id=user.id, period_days=days)
