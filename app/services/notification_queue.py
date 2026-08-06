"""Hybrid queue for dispatching notification jobs asynchronously."""

from __future__ import annotations

import threading as _threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core import metrics
from app.core.logging import get_logger
from app.tasks.notifications import (
    enqueue_comment_notification_task,
    enqueue_event_notification_task,
    enqueue_news_notification_task,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

# Global metrics instance for testing/monitoring
_queue_metrics: Any | None = None
# MOD-20-01 (audit 2026-03-24): Protected by threading.Lock for PEP 703
# free-threading safety.  Multiple async workers can append/clear
# concurrently — without a lock this causes data corruption.
_testing_failed_records: list[EnqueueFailure] = []
_testing_lock = _threading.Lock()


@dataclass(slots=True)
class DeadLetterCleanupConfig:
    """Configuration for dead-letter retention cleanup."""

    retention_days: int = 30
    interval_seconds: int = 86_400


async def enqueue_event_notification(
    event_id: uuid.UUID | int, *, locale: str | None = None
) -> None:
    """Enqueue an event notification job using NATS JetStream."""
    await enqueue_event_notification_task.kick(
        uuid.UUID(int=event_id) if isinstance(event_id, int) else event_id,
        locale=locale,
    )


async def enqueue_news_notification(
    news_id: uuid.UUID | int, *, locale: str | None = None
) -> None:
    """Enqueue a news notification job using NATS JetStream."""
    await enqueue_news_notification_task.kick(
        uuid.UUID(int=news_id) if isinstance(news_id, int) else news_id, locale=locale
    )


async def enqueue_comment_notification(
    news_id: uuid.UUID | int,
    comment_id: uuid.UUID | int,
    user_id: uuid.UUID | int,
    *,
    locale: str | None = None,
) -> None:
    """Enqueue a comment notification job using NATS JetStream."""
    await enqueue_comment_notification_task.kick(
        uuid.UUID(int=news_id) if isinstance(news_id, int) else news_id,
        uuid.UUID(int=comment_id) if isinstance(comment_id, int) else comment_id,
        uuid.UUID(int=user_id) if isinstance(user_id, int) else user_id,
        locale=locale,
    )


async def shutdown_notification_queue() -> None:
    """No-op for NATS JetStream-backed queue."""


async def cleanup_dead_lettered_jobs(retention_days: int = 30) -> int:
    """
    No-op: Dead letter cleanup is handled by NATS consumer tracking internally.
    """
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
    record_id: uuid.UUID | int
    locale: str | None = None


@dataclass
class EnqueueFailure:
    """Testing wrapper for failed enqueue records."""

    job: NotificationJob
    error: str
    source: str
    attempts: int = 1


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
    with _testing_lock:
        _testing_failed_records.append(EnqueueFailure(job, str(error), source))
    metrics.record_notification_failed(
        notification_type=job.kind, reason="enqueue_failure"
    )
    if _queue_metrics:
        try:
            _queue_metrics.enqueue_failures_total.labels(kind=job.kind).inc()
        except Exception:  # RZ-22-01-JUSTIFIED: metrics guard — best-effort metric recording (reviewed TD-27-04)
            logger.warning("Failed to record metric for enqueue failure", exc_info=True)


async def wait_for_all_jobs(timeout: float = 1.0) -> None:
    """Wait for all background jobs to complete (no-op in NATS mode for now)."""
    pass


async def reset_testing_state() -> None:
    """Reset testing state."""
    with _testing_lock:
        _testing_failed_records.clear()


async def get_failed_enqueue_records() -> list[EnqueueFailure]:
    """Get failed enqueue records for testing."""
    with _testing_lock:
        return list(_testing_failed_records)
