"""Notification cleanup functionality.

This module handles the cleanup of stale notifications and deliveries
based on retention policies.
"""

from __future__ import annotations

import datetime as dt
import logging
from datetime import UTC
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.core.database import async_session as _async_session
from app.models.models import Notification, NotificationDelivery

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = logging.getLogger(__name__)


async def cleanup_stale_notifications(
    *,
    db: AsyncSession | None = None,
    retention_days: int | None = None,
    now: dt.datetime | None = None,
) -> tuple[int, int]:
    """Remove notifications and deliveries older than the retention window.

    Unread notifications are preserved regardless of age. Returns a tuple with
    counts of deleted notifications and deliveries respectively.
    """

    if retention_days is None:
        retention_days = getattr(settings, "notifications_retention_days", 0) or 0

    retention_days = int(retention_days)

    if retention_days <= 0:
        return (0, 0)

    now_value = now or dt.datetime.now(UTC)

    if db is None:
        async with _async_session() as session:
            return await cleanup_stale_notifications(
                db=session, retention_days=retention_days, now=now_value
            )

    cutoff = now_value - dt.timedelta(days=int(retention_days))

    batch_size = int(getattr(settings, "notifications_retention_batch_size", 0) or 0)
    if batch_size <= 0:
        batch_size = 500

    deliveries_deleted = 0
    while True:
        deliveries_ids_stmt = (
            select(NotificationDelivery.id)
            .where(NotificationDelivery.attempted_at < cutoff)
            .order_by(NotificationDelivery.id)
            .limit(batch_size)
        )
        delivery_ids = [
            int(value)
            for value in (await db.scalars(deliveries_ids_stmt)).all()
            if value is not None
        ]
        if not delivery_ids:
            break
        deliveries_stmt = delete(NotificationDelivery).where(
            NotificationDelivery.id.in_(delivery_ids)
        )
        deliveries_result = await db.execute(deliveries_stmt)
        deliveries_deleted += int(deliveries_result.rowcount or 0)  # type: ignore[attr-defined]
        await db.commit()

    # Commit to close the transaction created by the final select above.
    await db.commit()

    notifications_deleted = 0
    while True:
        notifications_ids_stmt = (
            select(Notification.id)
            .where(
                Notification.created_at < cutoff,
                or_(Notification.read.is_(True), Notification.read_at.is_not(None)),
            )
            .order_by(Notification.id)
            .limit(batch_size)
        )
        notification_ids = [
            int(value)
            for value in (await db.scalars(notifications_ids_stmt)).all()
            if value is not None
        ]
        if not notification_ids:
            break
        notifications_stmt = delete(Notification).where(
            Notification.id.in_(notification_ids)
        )
        notifications_result = await db.execute(notifications_stmt)
        notifications_deleted += int(notifications_result.rowcount or 0)  # type: ignore[attr-defined]
        await db.commit()

    # Commit to close the transaction created by the final select above.
    await db.commit()

    if notifications_deleted or deliveries_deleted:
        logger.info(
            "Removed %s notifications and %s deliveries older than %s days",
            notifications_deleted,
            deliveries_deleted,
            retention_days,
        )

    return notifications_deleted, deliveries_deleted
