"""Transaction-scoped serialization for read-before-insert notification paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession


# The lock namespace is shared by every process that writes notifications.
_DEDUPE_LOCK = text(
    "SELECT pg_advisory_xact_lock("
    "hashtext('notification-dedupe'), hashtext(:dedupe_key))"
)


async def lock_notification_dedupe(db: AsyncDatabaseSession, dedupe_key: str) -> None:
    """Serialize a key until commit/rollback before querying existing rows.

    Notifications are partitioned by ``created_at``, so PostgreSQL cannot
    enforce a unique ``(user_id, dedupe_key)`` constraint on the parent table.
    SQLite tests run without the PostgreSQL-specific advisory lock.
    """
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(_DEDUPE_LOCK, {"dedupe_key": dedupe_key})
