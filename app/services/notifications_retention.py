from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.services.notifications import cleanup_stale_notifications

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)


_METRICS = get_periodic_task_metrics("notifications_retention")


@dataclass(slots=True)
class NotificationsRetentionConfig:
    retention_days: int = 90
    interval_seconds: int = 86_400

    def normalized_retention_days(self) -> int:
        return max(0, int(self.retention_days))

    def normalized_interval(self) -> int:
        return max(300, int(self.interval_seconds))


async def start_notifications_retention_scheduler(
    *, config: NotificationsRetentionConfig | None = None
) -> Callable[[], Awaitable[None]]:
    """Start background task that purges stale notifications periodically."""

    cfg = config or NotificationsRetentionConfig()
    retention_days = cfg.normalized_retention_days()
    if retention_days <= 0:

        async def _noop() -> None:
            return None

        logger.info(
            "Notifications retention scheduler disabled (retention_days=%s)",
            retention_days,
        )
        return _noop

    interval = cfg.normalized_interval()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        (
                            deleted_notifications,
                            deleted_deliveries,
                        ) = await cleanup_stale_notifications(
                            retention_days=retention_days
                        )
                        run.observe_deleted((deleted_notifications, deleted_deliveries))
                except asyncio.CancelledError:
                    raise
                except (OSError, ConnectionError):
                    # RZ-20-04: Narrowed — DB/network errors only.
                    logger.exception("Failed to cleanup stale notifications")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Notifications retention loop cancelled")
            raise

    loop = asyncio.get_running_loop()
    task = loop.create_task(_loop())

    async def _stop() -> None:
        if task.done():
            with suppress(asyncio.CancelledError, Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop
