from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.auth.mfa import purge_expired_challenges
from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("mfa_challenge_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MfaChallengeCleanupConfig:
    interval_seconds: int = settings.mfa_challenge_cleanup_interval_seconds
    grace_period_seconds: int = settings.mfa_challenge_cleanup_grace_period_seconds

    def normalized_interval(self) -> int:
        return max(30, int(self.interval_seconds))

    def normalized_grace_period(self) -> int:
        return max(0, int(self.grace_period_seconds))


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


async def start_mfa_challenge_cleanup_scheduler(
    *, config: MfaChallengeCleanupConfig | None = None
) -> Callable[[], Awaitable[None]]:
    cfg = config or MfaChallengeCleanupConfig()
    interval = cfg.normalized_interval()
    grace_period = cfg.normalized_grace_period()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        deleted = await cleanup_stale_mfa_challenges(
                            grace_period_seconds=grace_period
                        )
                        run.observe_deleted(deleted)
                except asyncio.CancelledError:
                    raise
                except (OSError, ConnectionError):
                    # RZ-20-04: Narrowed — DB/network errors only.
                    logger.exception("Failed to cleanup MFA challenges")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("MFA challenge cleanup loop cancelled")
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


if __name__ == "__main__":
    asyncio.run(cleanup_stale_mfa_challenges())
