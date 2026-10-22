"""Cleanup helpers for password reset tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.models import PasswordResetToken
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("password_reset_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_retention_minutes(value: int | None) -> int:
    if value is None:
        return RESET_TOKEN_EXPIRY_MINUTES
    return max(0, int(value))


async def cleanup_stale_password_reset_tokens(
    *,
    db: AsyncSession | None = None,
    now: datetime | None = None,
    retention_minutes: int | None = None,
) -> int:
    """Delete expired or long-lived used password reset tokens."""

    owns_session = db is None
    if now is None:
        now = _now()
    retention = _normalize_retention_minutes(retention_minutes)
    cutoff = now - timedelta(minutes=retention)

    if owns_session:
        async with async_session() as session:
            return await cleanup_stale_password_reset_tokens(
                db=session, now=now, retention_minutes=retention
            )

    assert db is not None  # noqa: S101
    stmt = delete(PasswordResetToken).where(
        or_(
            PasswordResetToken.expires_at <= now,
            and_(
                PasswordResetToken.used.is_(True),
                PasswordResetToken.created_at <= cutoff,
            ),
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("Removed %s stale password reset tokens", deleted)
    return deleted


if __name__ == "__main__":
    asyncio.run(cleanup_stale_password_reset_tokens())
