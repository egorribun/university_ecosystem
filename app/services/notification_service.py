from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import BackgroundTasks

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

from app.services import notification_queue
from app.services.notifications.delivery import create_notifications_for_users

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db

    async def dispatch_event_created(
        self, event_id: uuid.UUID | int, locale: str, background: BackgroundTasks
    ) -> None:
        """Enqueue event notification in background."""
        job = notification_queue.NotificationJob(
            kind="event", record_id=event_id, locale=locale
        )
        try:
            background.add_task(
                notification_queue.enqueue_event_notification,
                event_id,
                locale=locale,
            )
        except (RuntimeError, OSError) as exc:
            # RZ-20-04: Narrowed — enqueue errors (queue full, I/O).
            await notification_queue.record_enqueue_failure(
                job,
                error=exc,
                source="NotificationService.dispatch_event_created",
            )
            logger.exception(
                "Failed to enqueue event notification", extra={"event_id": event_id}
            )

    async def dispatch_news_created(
        self, news_id: uuid.UUID | int, locale: str, background: BackgroundTasks
    ) -> None:
        """Enqueue news notification in background."""
        try:
            background.add_task(
                notification_queue.enqueue_news_notification,
                news_id,
                locale=locale,
            )
        except (RuntimeError, OSError):
            # RZ-20-04: Narrowed — enqueue errors (queue full, I/O).
            logger.exception(
                "Failed to enqueue news notification", extra={"news_id": news_id}
            )

    async def dispatch_comment_created(
        self,
        news_id: uuid.UUID | int,
        comment_id: uuid.UUID | int,
        user_id: uuid.UUID | int,
        locale: str,
        background: BackgroundTasks,
    ) -> None:
        """Enqueue comment notification in background."""
        try:
            background.add_task(
                notification_queue.enqueue_comment_notification,
                news_id,
                comment_id,
                user_id,
                locale=locale,
            )
        except (RuntimeError, OSError):
            logger.exception(
                "Failed to enqueue comment notification",
                extra={"news_id": news_id, "comment_id": comment_id},
            )

    async def send_security_notification(
        self, user_ids: list[uuid.UUID | int], title: str, body: str
    ) -> int:
        """Directly create security notifications in the database."""
        return await create_notifications_for_users(
            self.db,
            title=title,
            body=body,
            type="security",
            user_ids=[uuid.UUID(str(uid)) for uid in user_ids],
        )
