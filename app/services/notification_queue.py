"""Hybrid queue for dispatching notification jobs asynchronously."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, true, update
from sqlalchemy.orm import aliased

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
    from app.services.audit_service import SecureAuditService

logger = get_logger(__name__)

# Global metrics instance for testing/monitoring
_queue_metrics: Any | None = None


class StaleDeadLetterSelectionError(ValueError):
    """The selected batch is not wholly present in the dead-letter queue."""


def _dead_letter_batch_digest(job_ids: list[uuid.UUID]) -> str:
    """Return a stable correlation key without retaining raw queue job IDs."""
    canonical = "\n".join(sorted(str(job_id) for job_id in job_ids))
    return sha256(canonical.encode("ascii")).hexdigest()


async def list_dead_lettered_jobs(
    db: AsyncDatabaseSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[NotificationQueueJob], int]:
    """Return one deterministic page and count from one database snapshot."""
    filter_clause = NotificationQueueJob.dead_lettered.is_(True)
    page = (
        select(NotificationQueueJob)
        .where(filter_clause)
        .order_by(
            NotificationQueueJob.enqueued_at.desc(),
            NotificationQueueJob.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .cte("notification_dead_letter_page")
    )
    total = (
        select(func.count(NotificationQueueJob.id).label("total"))
        .where(filter_clause)
        .cte("notification_dead_letter_total")
    )
    page_job = aliased(NotificationQueueJob, page)
    result = await db.execute(
        select(page_job, total.c.total)
        .select_from(total.outerjoin(page, true()))
        .order_by(page.c.enqueued_at.desc(), page.c.id.desc())
    )
    rows = result.all()
    jobs = [job for job, _ in rows if job is not None]
    total_count = int(rows[0][1]) if rows else 0
    return jobs, total_count


async def _lock_dead_lettered_jobs(
    db: AsyncDatabaseSession,
    job_ids: list[uuid.UUID],
) -> list[NotificationQueueJob]:
    """Lock an exact batch, rejecting stale or partially valid selections."""
    result = await db.execute(
        select(NotificationQueueJob)
        .where(
            NotificationQueueJob.id.in_(job_ids),
            NotificationQueueJob.dead_lettered.is_(True),
        )
        .with_for_update()
    )
    jobs = list(result.scalars().all())
    if len(jobs) != len(job_ids):
        raise StaleDeadLetterSelectionError("dead-letter selection is stale")
    return jobs


async def retry_dead_lettered_jobs(
    db: AsyncDatabaseSession,
    job_ids: list[uuid.UUID],
    *,
    audit: SecureAuditService,
    actor_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Atomically return a dead-letter batch and its audit event to the queue."""
    jobs = await _lock_dead_lettered_jobs(db, job_ids)
    retry_at = now or datetime.now(UTC)
    try:
        await db.execute(
            update(NotificationQueueJob)
            .where(NotificationQueueJob.id.in_([job.id for job in jobs]))
            .values(
                dead_lettered=False,
                claimed_at=None,
                attempts=0,
                last_error=None,
                next_retry_at=retry_at,
            )
        )
        await audit.record_domain_event(
            db,
            event_type="NOTIFICATION_DEAD_LETTER_RETRY",
            aggregate_type="notification_dead_letter_batch",
            aggregate_id=_dead_letter_batch_digest(job_ids),
            payload={"batch_count": len(jobs)},
            actor_id=actor_id,
        )
        await db.commit()
    except Exception:  # RZ-22-01-JUSTIFIED: rollback transaction before re-raising
        await db.rollback()
        raise
    return len(jobs)


async def purge_dead_lettered_jobs(
    db: AsyncDatabaseSession,
    job_ids: list[uuid.UUID],
    *,
    audit: SecureAuditService,
    actor_id: uuid.UUID,
) -> int:
    """Atomically delete a dead-letter batch and persist its audit event."""
    jobs = await _lock_dead_lettered_jobs(db, job_ids)
    try:
        await db.execute(
            delete(NotificationQueueJob).where(
                NotificationQueueJob.id.in_([job.id for job in jobs]),
                NotificationQueueJob.dead_lettered.is_(True),
            )
        )
        await audit.record_domain_event(
            db,
            event_type="NOTIFICATION_DEAD_LETTER_PURGE",
            aggregate_type="notification_dead_letter_batch",
            aggregate_id=_dead_letter_batch_digest(job_ids),
            payload={"batch_count": len(jobs)},
            actor_id=actor_id,
        )
        await db.commit()
    except Exception:  # RZ-22-01-JUSTIFIED: rollback transaction before re-raising
        await db.rollback()
        raise
    return len(jobs)


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

    # The cutoff must be computed from a UTC-normalized instant.  Keeping the
    # normalized value explicit prevents a local-time conversion from silently
    # changing the retention boundary on hosts configured outside UTC.
    normalized_current = current.astimezone(UTC)
    cutoff = normalized_current - timedelta(days=retention_days)
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
    try:
        rowcount = getattr(result, "rowcount")  # noqa: B009
    except AttributeError:
        deleted = 0
    else:
        deleted = 0 if rowcount is None else int(rowcount)
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
