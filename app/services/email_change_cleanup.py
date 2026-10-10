"""Cleanup helpers for email change tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, update

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.models import EmailChangeToken
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

if TYPE_CHECKING:
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


if __name__ == "__main__":
    asyncio.run(cleanup_stale_email_change_tokens())
