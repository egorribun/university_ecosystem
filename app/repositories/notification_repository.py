"""
Notification repository for notification data access operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.notifications import Notification
from app.repositories.base import BaseRepository
from app.schemas.dtos.notification import NotificationDTO

if TYPE_CHECKING:
    import uuid

    from app.core.protocols import AsyncDatabaseSession


class NotificationRepository(
    BaseRepository[Notification, NotificationDTO, dict[str, Any], dict[str, Any]]
):
    """Repository for Notification model operations."""

    @property
    def model(self) -> type[Notification]:
        return Notification

    @property
    def dto_class(self) -> type[NotificationDTO]:
        return NotificationDTO

    async def get_for_user(
        self,
        user_id: uuid.UUID | str | int,
        *,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[NotificationDTO]:
        """Get notifications for a user, ordered by creation date descending."""
        stmt = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            stmt = stmt.where(Notification.read.is_(False))

        stmt = stmt.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return [self._to_dto(row) for row in result.scalars().all()]


def get_notification_repository(db: AsyncDatabaseSession) -> NotificationRepository:
    """Factory function for dependency injection."""
    return NotificationRepository(db)


__all__ = ["NotificationRepository", "get_notification_repository"]
