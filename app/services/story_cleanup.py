"""Utilities for removing expired stories from the database."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.models import Story

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("story_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


async def cleanup_expired_stories(
    *, db: AsyncSession | None = None, now: datetime | None = None
) -> int:
    """Remove stories whose expiration timestamp has already passed."""

    owns_session = db is None
    if now is None:
        now = _now()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    if owns_session:
        async with async_session() as session:
            return await cleanup_expired_stories(db=session, now=now)

    assert db is not None  # noqa: S101
    stmt = delete(Story).where(Story.expires_at <= now)
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    await db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("Removed %s expired stories", deleted)
    return deleted


if __name__ == "__main__":
    asyncio.run(cleanup_expired_stories())
