"""Notification delivery statistics.

This module provides functionality for aggregating notification
delivery statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.models import NotificationDelivery

if TYPE_CHECKING:
    import datetime as dt

    from app.core.protocols import AsyncDatabaseSession as AsyncSession


async def aggregate_notification_delivery_stats(
    db: AsyncSession,
    *,
    since: dt.datetime | None = None,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate notification delivery statistics grouped by channel and status."""
    stmt = select(
        NotificationDelivery.channel,
        NotificationDelivery.status,
        func.count(NotificationDelivery.id).label("count"),
        func.count(NotificationDelivery.delivered_at).label("delivered"),
        func.min(NotificationDelivery.attempted_at).label("first_attempt_at"),
        func.max(NotificationDelivery.attempted_at).label("last_attempt_at"),
    ).group_by(NotificationDelivery.channel, NotificationDelivery.status)

    if since is not None:
        stmt = stmt.where(NotificationDelivery.attempted_at >= since)
    if channel is not None:
        stmt = stmt.where(NotificationDelivery.channel == channel)

    result = await db.execute(stmt)
    stats: list[dict[str, Any]] = []
    for row in result:
        m = row._mapping
        stats.append(
            {
                "channel": m["channel"],
                "status": m["status"],
                "count": int(m["count"] or 0),
                "delivered": int(m["delivered"] or 0),
                "first_attempt_at": m["first_attempt_at"],
                "last_attempt_at": m["last_attempt_at"],
            }
        )
    return stats
