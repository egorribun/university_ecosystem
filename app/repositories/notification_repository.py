"""
Notification repository for notification data access operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select, update

from app.models.notifications import Notification
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class NotificationRepository(BaseRepository[Notification, dict, dict]):
    """Repository for Notification model operations."""

    @property
    def model(self) -> type[Notification]:
        return Notification

    async def get_for_user(
        self,
        user_id: uuid.UUID | str | int,
        *,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[Notification]:
        """Get notifications for a user, ordered by creation date descending."""
        stmt = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            stmt = stmt.where(Notification.read.is_(False))

        stmt = stmt.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_unread_for_user(
        self, user_id: uuid.UUID | str | int, *, limit: int = 50
    ) -> list[Notification]:
        """Get unread notifications for a user."""
        return await self.get_for_user(user_id, limit=limit, unread_only=True)

    async def count_unread(self, user_id: uuid.UUID | str | int) -> int:
        """Count unread notifications for a user."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.read.is_(False),
                )
            )
        )
        return result.scalar() or 0

    async def mark_as_read(
        self,
        notification_ids: list[uuid.UUID | str | int],
        user_id: uuid.UUID | str | int,
    ) -> int:
        """Mark notifications as read. Returns count of updated records."""
        if not notification_ids:
            return 0

        now = datetime.now(UTC)
        result = await self.db.execute(
            update(Notification)
            .where(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id,
                    Notification.read.is_(False),
                )
            )
            .values(read=True, read_at=now)
        )
        await self.db.flush()
        return result.rowcount or 0

    async def mark_all_as_read(self, user_id: uuid.UUID | str | int) -> int:
        """Mark all notifications as read for a user."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.read.is_(False),
                )
            )
            .values(read=True, read_at=now)
        )
        await self.db.flush()
        return result.rowcount or 0

    async def get_by_dedupe_key(
        self, user_id: uuid.UUID | str | int, dedupe_key: str
    ) -> Notification | None:
        """Get notification by deduplication key."""
        result = await self.db.execute(
            select(Notification).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.dedupe_key == dedupe_key,
                )
            )
        )
        return result.scalars().first()

    async def count_by_type(self, user_id: uuid.UUID | str | int) -> dict[str, int]:
        """Count notifications by type for a user."""
        result = await self.db.execute(
            select(Notification.type, func.count(Notification.id))
            .where(Notification.user_id == user_id)
            .group_by(Notification.type)
        )
        return {row[0] or "unknown": row[1] for row in result.all()}


def get_notification_repository(db: AsyncSession) -> NotificationRepository:
    """Factory function for dependency injection."""
    return NotificationRepository(db)


__all__ = ["NotificationRepository", "get_notification_repository"]
