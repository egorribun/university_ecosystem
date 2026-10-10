from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.auth.mfa import purge_expired_challenges
from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("mfa_challenge_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


async def cleanup_stale_mfa_challenges(
    *,
    db: AsyncSession | None = None,
    grace_period_seconds: int | None = None,
    now: datetime | None = None,
) -> int:
    owns_session = db is None
    if grace_period_seconds is None:
        grace_period_seconds = settings.mfa_challenge_cleanup_grace_period_seconds
    grace_period_seconds = max(0, int(grace_period_seconds))
    if now is None:
        now = _now()

    if owns_session:
        async with async_session() as session:
            return await cleanup_stale_mfa_challenges(
                db=session,
                grace_period_seconds=grace_period_seconds,
                now=now,
            )

    assert db is not None  # noqa: S101
    deleted = await purge_expired_challenges(
        db,
        grace_period_seconds=grace_period_seconds,
        now=now,
    )
    await db.commit()
    logger.info(
        "Removed %s stale MFA challenges (grace=%s seconds)",
        deleted,
        grace_period_seconds,
    )
    return deleted


if __name__ == "__main__":
    asyncio.run(cleanup_stale_mfa_challenges())
