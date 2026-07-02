"""Cleanup helpers for email change tokens."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, update

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.models import EmailChangeToken
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("email_change_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_retention_minutes(value: int | None) -> int:
    if value is None:
        return RESET_TOKEN_EXPIRY_MINUTES
    return max(0, int(value))


async def cleanup_stale_email_change_tokens(
    *,
    db: AsyncSession | None = None,
    now: datetime | None = None,
    retention_minutes: int | None = None,
) -> int:
    """Delete or deactivate stale email change tokens."""

    owns_session = db is None
    if now is None:
        now = _now()
    retention = _normalize_retention_minutes(retention_minutes)
    cutoff = now - timedelta(minutes=retention)

    if owns_session:
        async with async_session() as session:
            return await cleanup_stale_email_change_tokens(
                db=session, now=now, retention_minutes=retention
            )

    assert db is not None  # noqa: S101
    removed = await db.execute(
        delete(EmailChangeToken).where(EmailChangeToken.created_at <= cutoff)
    )
    marked = await db.execute(
        update(EmailChangeToken)
        .where(
            EmailChangeToken.used.is_(False),
            EmailChangeToken.expires_at <= now,
            EmailChangeToken.created_at > cutoff,
        )
        .values(used=True)
    )
    await db.commit()

    updated_count = int(getattr(marked, "rowcount", 0) or 0)
    removed_count = int(getattr(removed, "rowcount", 0) or 0)
    total = updated_count + removed_count
    if total:
        logger.info(
            "Cleaned %s pending address-change records (marked=%s, removed=%s)",
            total,
            updated_count,
            removed_count,
        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
    return total


@dataclass(slots=True)
class EmailChangeCleanupConfig:
    interval_seconds: int = 3_600
    retention_minutes: int | None = None

    def normalized_interval(self) -> int:
        return max(30, int(self.interval_seconds))

    def normalized_retention_minutes(self) -> int:
        return _normalize_retention_minutes(self.retention_minutes)


async def start_email_change_cleanup_scheduler(
    *, config: EmailChangeCleanupConfig | None = None
) -> Callable[[], Awaitable[None]]:
    """Start a background task that cleans up stale email change tokens."""

    cfg = config or EmailChangeCleanupConfig()
    interval = cfg.normalized_interval()
    retention = cfg.normalized_retention_minutes()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        cleaned = await cleanup_stale_email_change_tokens(
                            retention_minutes=retention
                        )
                        run.observe_deleted(cleaned)
                except asyncio.CancelledError:
                    raise
                except (OSError, ConnectionError):
                    # RZ-20-04 (audit 2026-03-24): Narrowed — DB/network errors only.
                    # Logic bugs (TypeError, KeyError) now propagate to Sentry.
                    logger.exception("Failed to cleanup pending address-change records")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Address-change cleanup loop cancelled")
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


if __name__ == "__main__":
    asyncio.run(cleanup_stale_email_change_tokens())
