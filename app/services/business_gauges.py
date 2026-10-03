"""Refresh the product gauges that cannot be incremented from a request path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.metrics import set_active_users, set_mfa_adoption
from app.core.protocols import AsyncDatabaseSession
from app.models import ActiveSession, User

logger = get_logger(__name__)

_PERIODS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


async def refresh_business_gauges(
    *, db: AsyncDatabaseSession | None = None, now: datetime | None = None
) -> dict[str, int]:
    """Set active-user (daily/weekly) and MFA-adoption gauges; returns the values."""
    if db is None:
        async with async_session() as session:
            return await refresh_business_gauges(db=session, now=now)

    now = now or datetime.now(UTC)
    values: dict[str, int] = {}
    for period, window in _PERIODS.items():
        active = await db.scalar(
            select(func.count(func.distinct(ActiveSession.user_id))).where(
                ActiveSession.last_seen_at >= now - window,
                ActiveSession.revoked_at.is_(None),
            )
        )
        values[period] = int(active or 0)
        set_active_users(values[period], period=period)

    enrolled = await db.scalar(
        select(func.count(User.id)).where(
            User.is_active.is_(True), User.mfa_default_method.is_not(None)
        )
    )
    values["mfa"] = int(enrolled or 0)
    set_mfa_adoption(values["mfa"])
    logger.debug("business_gauges_refreshed", extra=values)
    return values
