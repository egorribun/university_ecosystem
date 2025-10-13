"""Async worker responsible for generating notification reminders."""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from typing import Awaitable, Callable

from app.core.config import settings
from app.core.database import async_session, wait_db
from app.core.observability import (
    WorkerMetrics,
    configure_worker_observability,
    create_worker_metrics,
    create_worker_monitoring_app,
    start_worker_monitoring_server,
)
from app.services.notifications import generate_schedule_reminders

logger = logging.getLogger(__name__)


class NotificationsScheduler:
    """Run the schedule reminder generator on a fixed interval."""

    def __init__(
        self,
        *,
        poll_seconds: int,
        window_minutes: int,
        max_backoff_seconds: int,
        metrics: WorkerMetrics | None = None,
    ) -> None:
        self.poll_seconds = max(1, int(poll_seconds))
        self.window_minutes = max(1, int(window_minutes))
        self.max_backoff_seconds = max(1, int(max_backoff_seconds))
        self.metrics = metrics

    async def run_once(self) -> int:
        async with async_session() as db:
            created = await generate_schedule_reminders(
                db, window_minutes=self.window_minutes
            )
        return created

    async def run_forever(self) -> None:
        consecutive_failures = 0

        try:
            while True:
                sleep_for = self.poll_seconds
                try:
                    created = await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    consecutive_failures += 1
                    sleep_for = min(
                        self.poll_seconds * (2 ** min(consecutive_failures, 5)),
                        self.max_backoff_seconds,
                    )
                    if self.metrics is not None:
                        self.metrics.record_failure()
                    logger.exception(
                        "Failed to generate schedule reminders (attempt %s)",
                        consecutive_failures,
                    )
                    logging.getLogger().error(
                        "Failed to generate schedule reminders (attempt %s)",
                        consecutive_failures,
                    )
                else:
                    consecutive_failures = 0
                    if self.metrics is not None:
                        self.metrics.record_success(created)
                    if created:
                        logger.info(
                            "Generated %s schedule reminder notifications", created
                        )
                await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            logger.info("Notifications scheduler loop cancelled")
            raise


_scheduler_task: asyncio.Task[None] | None = None


async def start_notifications_scheduler(
    *,
    poll_seconds: int | None = None,
    window_minutes: int | None = None,
    max_backoff_seconds: int | None = None,
    metrics: WorkerMetrics | None = None,
) -> Callable[[], Awaitable[None]]:
    """Start the notifications scheduler in the current event loop."""

    global _scheduler_task

    poll = (
        poll_seconds
        if poll_seconds is not None
        else settings.notifications_scheduler_poll_seconds
    )
    window = (
        window_minutes
        if window_minutes is not None
        else settings.notifications_scheduler_window_minutes
    )
    backoff = (
        max_backoff_seconds
        if max_backoff_seconds is not None
        else settings.notifications_scheduler_max_backoff_seconds
    )

    async def _stop_task(task: asyncio.Task[None]) -> None:
        if task.done():
            with suppress(Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    if _scheduler_task and not _scheduler_task.done():
        existing = _scheduler_task

        async def _stop_existing() -> None:
            global _scheduler_task
            await _stop_task(existing)
            if _scheduler_task is existing:
                _scheduler_task = None

        return _stop_existing

    scheduler = NotificationsScheduler(
        poll_seconds=poll,
        window_minutes=window,
        max_backoff_seconds=backoff,
        metrics=metrics,
    )
    loop = asyncio.get_running_loop()
    task = loop.create_task(scheduler.run_forever())
    _scheduler_task = task

    async def _stop() -> None:
        global _scheduler_task
        await _stop_task(task)
        if _scheduler_task is task:
            _scheduler_task = None

    return _stop


async def _wait_for_signals(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    handled_signals = [signal.SIGINT, signal.SIGTERM]

    def _handler(*_: object) -> None:
        stop_event.set()

    for sig in handled_signals:
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:  # pragma: no cover - Windows fallback
            signal.signal(sig, lambda *_: stop_event.set())

    await stop_event.wait()


async def run_worker() -> None:
    """Entrypoint for the standalone notifications worker."""

    configure_worker_observability(worker_name="notifications")
    metrics = create_worker_metrics("notifications_scheduler")

    monitor_stop: Callable[[], Awaitable[None]] | None = None
    metrics_port = settings.notifications_worker_metrics_port
    if metrics_port and metrics_port > 0:
        monitor_app = create_worker_monitoring_app(
            worker_name="notifications", metrics=metrics
        )
        monitor_stop = await start_worker_monitoring_server(
            monitor_app,
            host=settings.notifications_worker_metrics_host,
            port=metrics_port,
        )

    await wait_db(max_attempts=10, delay=1.0)

    scheduler = NotificationsScheduler(
        poll_seconds=settings.notifications_scheduler_poll_seconds,
        window_minutes=settings.notifications_scheduler_window_minutes,
        max_backoff_seconds=settings.notifications_scheduler_max_backoff_seconds,
        metrics=metrics,
    )

    logger.info(
        "Notifications worker starting (poll=%ss, window=%smin)",
        scheduler.poll_seconds,
        scheduler.window_minutes,
    )

    scheduler_task = asyncio.create_task(scheduler.run_forever())
    stop_event = asyncio.Event()
    signal_task = asyncio.create_task(_wait_for_signals(stop_event))

    done, pending = await asyncio.wait(
        {scheduler_task, signal_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if scheduler_task in done:
        with suppress(asyncio.CancelledError):
            await scheduler_task
        stop_event.set()
    else:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    if monitor_stop is not None:
        await monitor_stop()

    logger.info("Notifications worker stopped")


async def main() -> None:
    await run_worker()


if __name__ == "__main__":
    asyncio.run(main())
