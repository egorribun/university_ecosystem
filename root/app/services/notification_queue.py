"""Hybrid queue for dispatching notification jobs asynchronously."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.tasks.notifications import (
    enqueue_event_notification_task,
    enqueue_news_notification_task,
)

logger = logging.getLogger(__name__)

# Global metrics instance for testing/monitoring
_queue_metrics: Any | None = None


@dataclass(slots=True)
class DeadLetterCleanupConfig:
    """Configuration for dead-letter retention cleanup."""

    retention_days: int = 30
    interval_seconds: int = 86_400


async def enqueue_event_notification(
    event_id: int, *, locale: str | None = None
) -> None:
    """Enqueue an event notification job using TaskIQ."""
    await enqueue_event_notification_task.kiq(event_id, locale=locale)


async def enqueue_news_notification(news_id: int, *, locale: str | None = None) -> None:
    """Enqueue a news notification job using TaskIQ."""
    await enqueue_news_notification_task.kiq(news_id, locale=locale)


async def shutdown_notification_queue() -> None:
    """No-op for TaskIQ-backed queue."""


async def cleanup_dead_lettered_jobs(retention_days: int = 30) -> int:
    """No-op: Dead letter cleanup is not supported in TaskIQ mode (or handled by TaskIQ)."""
    return 0


async def start_dead_letter_cleanup_scheduler(
    config: DeadLetterCleanupConfig,
) -> Callable[[], Awaitable[None]]:
    """No-op scheduler."""

    async def stop() -> None:
        pass

    return stop





@dataclass
class NotificationJob:
    """Legacy dataclass for notification context."""

    kind: str
    record_id: int
    locale: str | None = None


async def record_enqueue_failure(
    job: NotificationJob,
    error: Exception,
    source: str,
) -> None:
    """Log failure to enqueue notification."""
    logger.error(
        "Failed to enqueue %s notification for ID %s (source=%s): %s",
        job.kind,
        job.record_id,
        source,
        error,
    )
    if _queue_metrics:
        try:
            _queue_metrics.enqueue_failures_total.labels(kind=job.kind).inc()
        except Exception:
            logger.warning("Failed to record metric for enqueue failure", exc_info=True)


async def wait_for_all_jobs(timeout: float = 1.0) -> None:
    """No-op stub for waiting for jobs."""
    pass


async def reset_testing_state() -> None:
    """No-op for testing state reset."""
    pass
