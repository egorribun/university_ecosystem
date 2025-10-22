"""Utilities for removing expired stories from the database."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.models import Story

logger = logging.getLogger(__name__)


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

    stmt = delete(Story).where(Story.expires_at <= now)
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    await db.commit()
    deleted = int(result.rowcount or 0)
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
                    await cleanup_expired_stories()
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Failed to cleanup expired stories")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Story cleanup loop cancelled")
            raise

    loop = asyncio.get_running_loop()
    task = loop.create_task(_loop())

    async def _stop() -> None:
        if task.done():
            with suppress(Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    asyncio.run(cleanup_expired_stories())
