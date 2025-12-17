"""Notification delivery statistics.

This module provides functionality for aggregating notification
delivery statistics.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NotificationDelivery


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
        stats.append(
            {
                "channel": row.channel,
                "status": row.status,
                "count": int(row.count or 0),
                "delivered": int(row.delivered or 0),
                "first_attempt_at": row.first_attempt_at,
                "last_attempt_at": row.last_attempt_at,
            }
        )
    return stats
