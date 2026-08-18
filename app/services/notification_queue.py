"""Hybrid queue for dispatching notification jobs asynchronously."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete

from app.core import metrics
from app.core.database import async_session
from app.core.logging import get_logger
from app.models import NotificationQueueJob
from app.tasks.notifications import (
    enqueue_comment_notification_task,
    enqueue_event_notification_task,
    enqueue_news_notification_task,
)

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

logger = get_logger(__name__)

# Global metrics instance for testing/monitoring
_queue_metrics: Any | None = None


async def enqueue_event_notification(
    event_id: uuid.UUID | int, *, locale: str | None = None
) -> None:
    """Enqueue an event notification job using NATS JetStream."""
    normalized_id = uuid.UUID(int=event_id) if isinstance(event_id, int) else event_id
    try:
        await enqueue_event_notification_task.kick(normalized_id, locale=locale)
    except (RuntimeError, OSError) as exc:
        await report_enqueue_failure(
            notification_type="event",
            record_id=normalized_id,
            error=exc,
            source="enqueue_event_notification",
        )
        raise


async def enqueue_news_notification(
    news_id: uuid.UUID | int, *, locale: str | None = None
) -> None:
    """Enqueue a news notification job using NATS JetStream."""
    normalized_id = uuid.UUID(int=news_id) if isinstance(news_id, int) else news_id
    try:
        await enqueue_news_notification_task.kick(normalized_id, locale=locale)
    except (RuntimeError, OSError) as exc:
        await report_enqueue_failure(
            notification_type="news",
            record_id=normalized_id,
            error=exc,
            source="enqueue_news_notification",
        )
        raise


async def enqueue_comment_notification(
    news_id: uuid.UUID | int,
    comment_id: uuid.UUID | int,
    user_id: uuid.UUID | int,
    *,
    locale: str | None = None,
) -> None:
    """Enqueue a comment notification job using NATS JetStream."""
    normalized_news_id = uuid.UUID(int=news_id) if isinstance(news_id, int) else news_id
    normalized_comment_id = (
        uuid.UUID(int=comment_id) if isinstance(comment_id, int) else comment_id
    )
    normalized_user_id = uuid.UUID(int=user_id) if isinstance(user_id, int) else user_id
    try:
        await enqueue_comment_notification_task.kick(
            normalized_news_id,
            normalized_comment_id,
            normalized_user_id,
            locale=locale,
        )
    except (RuntimeError, OSError) as exc:
        await report_enqueue_failure(
            notification_type="comment",
            record_id=normalized_comment_id,
            error=exc,
            source="enqueue_comment_notification",
        )
        raise


async def cleanup_dead_lettered_jobs(
    retention_days: int = 30,
    *,
    db: AsyncDatabaseSession | None = None,
    now: datetime | None = None,
) -> int:
    """Delete legacy queue rows dead-lettered before the retention cutoff."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    if db is None:
        async with async_session() as session:
            return await cleanup_dead_lettered_jobs(
                retention_days,
                db=session,
                now=current,
            )

    cutoff = current - timedelta(days=retention_days)
    statement = (
        delete(NotificationQueueJob)
        .where(
            NotificationQueueJob.dead_lettered.is_(True),
            NotificationQueueJob.enqueued_at <= cutoff,
        )
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(statement)
    await db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("Removed %s expired notification queue dead letters", deleted)
    return deleted


async def report_enqueue_failure(
    *,
    notification_type: str,
    record_id: uuid.UUID | int,
    error: Exception,
    source: str,
) -> None:
    """Report a queue failure without retaining unbounded in-process state."""
    logger.error(
        "Failed to enqueue %s notification for ID %s (source=%s): %s",
        notification_type,
        record_id,
        source,
        error,
    )
    metrics.record_notification_failed(
        notification_type=notification_type, reason="enqueue_failure"
    )
    if _queue_metrics:
        try:
            _queue_metrics.enqueue_failures_total.labels(kind=notification_type).inc()
        except Exception:  # RZ-22-01-JUSTIFIED: metrics guard — best-effort metric recording (reviewed TD-27-04)
            logger.warning("Failed to record metric for enqueue failure", exc_info=True)
