"""Utilities for removing expired stories from the database."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.models import Story

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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


@dataclass(slots=True)
class StoryCleanupConfig:
    interval_seconds: int = 86_400

    def normalized_interval(self) -> int:
        return max(60, int(self.interval_seconds))


async def start_story_cleanup_scheduler(
    *, config: StoryCleanupConfig | None = None
) -> Callable[[], Awaitable[None]]:
    """Start a background task that periodically removes expired stories."""

    cfg = config or StoryCleanupConfig()
    interval = cfg.normalized_interval()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        deleted = await cleanup_expired_stories()
                        run.observe_deleted(deleted)
                except asyncio.CancelledError:
                    raise
                except (OSError, ConnectionError):  # pragma: no cover
                    # RZ-20-04: Narrowed — DB/network errors only.
                    logger.exception("Failed to cleanup expired stories")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Story cleanup loop cancelled")
            raise

    loop = asyncio.get_running_loop()
    task = loop.create_task(_loop())

    async def _stop() -> None:
        if task.done():
            with suppress(Exception, asyncio.CancelledError):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    asyncio.run(cleanup_expired_stories())
