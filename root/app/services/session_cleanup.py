"""Utilities for removing expired authentication sessions."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.observability import get_periodic_task_metrics
from app.models.models import ActiveSession, MfaChallenge

logger = logging.getLogger(__name__)


_METRICS = get_periodic_task_metrics("session_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


async def cleanup_expired_sessions(
    *, db: AsyncSession | None = None, now: datetime | None = None
) -> int:
    """Remove sessions where the expiry or revocation timestamp has passed."""

    owns_session = db is None
    if now is None:
        now = _now()
    if owns_session:
        async with async_session() as session:
            return await cleanup_expired_sessions(db=session, now=now)

    target_sessions_stmt = select(ActiveSession.id).where(
        or_(ActiveSession.expires_at <= now, ActiveSession.revoked_at <= now)
    )
    result = await db.execute(target_sessions_stmt)
    session_ids = [row[0] for row in result]
    deleted = 0
    if session_ids:
        await db.execute(
            delete(MfaChallenge).where(MfaChallenge.session_id.in_(session_ids))
        )
        delete_stmt = delete(ActiveSession).where(ActiveSession.id.in_(session_ids))
        delete_result = await db.execute(delete_stmt)
        deleted = int(delete_result.rowcount or 0)
    await db.commit()
    if deleted:
        logger.info("Removed %s expired sessions", deleted)
    return deleted


@dataclass(slots=True)
class SessionCleanupConfig:
    interval_seconds: int = 900

    def normalized_interval(self) -> int:
        return max(30, int(self.interval_seconds))


async def start_session_cleanup_scheduler(
    *, config: SessionCleanupConfig | None = None
) -> Callable[[], Awaitable[None]]:
    """Start background cleanup task for expired sessions."""

    cfg = config or SessionCleanupConfig()
    interval = cfg.normalized_interval()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        deleted = await cleanup_expired_sessions()
                        run.observe_deleted(deleted)
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Failed to cleanup expired sessions")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Session cleanup loop cancelled")
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
    asyncio.run(cleanup_expired_sessions())
