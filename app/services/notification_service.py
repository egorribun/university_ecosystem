from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

from app.services.notifications.delivery import create_notifications_for_users

logger = get_logger(__name__)


def _coerce_user_id(value: uuid.UUID | int) -> uuid.UUID:
    """Normalize UUID and legacy integer identifiers for the UUID schema."""

    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(int=value)


class NotificationService:
    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db

    async def send_security_notification(
        self, user_ids: list[uuid.UUID | int], title: str, body: str
    ) -> int:
        """Directly create security notifications in the database."""
        return await create_notifications_for_users(
            self.db,
            title=title,
            body=body,
            type="security",
            user_ids=[_coerce_user_id(uid) for uid in user_ids],
        )
