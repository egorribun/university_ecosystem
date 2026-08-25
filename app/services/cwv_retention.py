"""Bounded retention for pseudonymous field Core Web Vitals evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete

from app.core.database import async_session
from app.models.cwv import CwvObservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def cleanup_stale_cwv_observations(
    *,
    db: AsyncSession | None = None,
    now: datetime | None = None,
    retention_days: int,
) -> int:
    """Delete CWV rows beyond the configured bounded retention period."""

    if retention_days < 1:
        raise ValueError("CWV retention must be at least one day")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if db is None:
        async with async_session() as session:
            return await cleanup_stale_cwv_observations(
                db=session,
                now=current,
                retention_days=retention_days,
            )
    result = await db.execute(
        delete(CwvObservation).where(
            CwvObservation.created_at < current - timedelta(days=retention_days)
        )
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)
