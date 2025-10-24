"""Hybrid queue for dispatching notification jobs asynchronously."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, cast
from weakref import WeakKeyDictionary

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.core.observability import (
    NotificationQueueMetrics,
    get_notification_queue_metrics,
)
from app.models.models import Event, News, Notification, NotificationQueueJob
from app.services.notifications import notify_about_event, notify_about_news

logger = logging.getLogger(__name__)


JobKind = Literal["event", "news"]


@dataclass(slots=True, frozen=True)
class NotificationJob:
    """Queued notification delivery request."""

    kind: JobKind
    record_id: int
    locale: str | None
    queue_id: int | None = None


@dataclass(slots=True)
class _LoopState:
    """Per-event-loop resources for the notification queue."""

    queue: asyncio.Queue[NotificationJob]
    worker_task: asyncio.Task[None] | None
    worker_lock: asyncio.Lock
    job_event: asyncio.Event
    active_jobs: int = 0


_loop_states: "WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopState]" = (
    WeakKeyDictionary()
)


_queue_metrics: NotificationQueueMetrics | None = None


def _get_metrics() -> NotificationQueueMetrics | None:
    global _queue_metrics
    if _queue_metrics is None:
        try:
            _queue_metrics = get_notification_queue_metrics()
        except RuntimeError:  # pragma: no cover - optional dependency
            _queue_metrics = None
    return _queue_metrics


def _use_persistent_backend() -> bool:
    return not getattr(settings, "notifications_queue_in_memory_only", False)


def _get_loop_state() -> _LoopState:
    loop = asyncio.get_running_loop()
    state = _loop_states.get(loop)
    if state is None:
        state = _LoopState(
            queue=asyncio.Queue(maxsize=max(0, settings.notifications_queue_max_size)),
            worker_task=None,
            worker_lock=asyncio.Lock(),
            job_event=asyncio.Event(),
        )
        _loop_states[loop] = state
    metrics = _get_metrics()
    if metrics is not None:
        if _use_persistent_backend():
            loop.create_task(_refresh_persistent_queue_size(metrics))
        else:
            metrics.queue_size.set(state.queue.qsize())
    return state


_WORKER_TASK_NAME = "notification-queue-worker"


async def _ensure_worker() -> None:
    """Ensure that a background worker is running to process queued jobs."""

    state = _get_loop_state()

    if state.worker_task and not state.worker_task.done():
        return

    async with state.worker_lock:
        if state.worker_task and not state.worker_task.done():
            return
        loop = asyncio.get_running_loop()
        state.worker_task = loop.create_task(
            _worker_loop(state), name=_WORKER_TASK_NAME
        )


async def _worker_loop(state: _LoopState) -> None:
    """Continuously process notification jobs from the queue."""

    metrics = _get_metrics()
    try:
        while True:
            if _use_persistent_backend():
                job = await _dequeue_persistent_job(state)
            else:
                job = await state.queue.get()
                state.active_jobs += 1
                if metrics is not None:
                    metrics.queue_size.set(state.queue.qsize())
            started = time.perf_counter()
            success = False
            error: BaseException | None = None
            try:
                await _process_job(job)
                success = True
            except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
                raise
            except Exception as exc:  # pragma: no cover - defensive guard
                error = exc
                logger.exception(
                    "Failed to process notification job", extra={"job": job}
                )
            finally:
                if metrics is not None:
                    elapsed = max(time.perf_counter() - started, 0.0)
                    metrics.processing_latency_seconds.observe(elapsed)
                if _use_persistent_backend():
                    await _acknowledge_persistent_job(
                        job,
                        success=success,
                        error=error,
                        state=state,
                        metrics=metrics,
                    )
                else:
                    state.queue.task_done()
                state.active_jobs = max(state.active_jobs - 1, 0)
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


def _evict_oldest(queue: asyncio.Queue[NotificationJob]) -> NotificationJob | None:
    try:
        job = queue.get_nowait()
    except asyncio.QueueEmpty:
        return None
    else:
        queue.task_done()
        return job


async def _enqueue_job(job: NotificationJob) -> None:
    if _use_persistent_backend():
        await _enqueue_persistent_job(job)
    else:
        await _enqueue_in_memory_job(job)


async def _enqueue_in_memory_job(job: NotificationJob) -> None:
    state = _get_loop_state()
    queue = state.queue
    metrics = _get_metrics()
    timeout = max(float(settings.notifications_queue_enqueue_timeout_seconds), 0.0)
    enqueued = False

    try:
        queue.put_nowait(job)
    except asyncio.QueueFull:
        evicted = _evict_oldest(queue)
        if metrics is not None:
            metrics.dropped_jobs_total.inc()
            metrics.queue_size.set(queue.qsize())
        logger.warning(
            "Notification queue full; dropped oldest job",
            extra={"dropped_job": evicted, "job": job},
        )
        if timeout > 0:
            try:
                await asyncio.wait_for(queue.put(job), timeout=timeout)
                enqueued = True
            except asyncio.TimeoutError:
                if metrics is not None:
                    metrics.dropped_jobs_total.inc()
                    metrics.queue_size.set(queue.qsize())
                logger.warning(
                    "Notification queue saturated; dropping job after timeout",
                    extra={"job": job},
                )
                return
        else:
            if metrics is not None:
                metrics.queue_size.set(queue.qsize())
            logger.warning(
                "Notification queue saturated; dropping job without timeout",
                extra={"job": job},
            )
            return
    else:
        enqueued = True
    if metrics is not None:
        metrics.queue_size.set(queue.qsize())
    if enqueued:
        await _ensure_worker()


async def _enqueue_persistent_job(job: NotificationJob) -> None:
    metrics = _get_metrics()
    state = _get_loop_state()
    try:
        async with async_session() as session:
            async with session.begin():
                record = NotificationQueueJob(
                    kind=job.kind,
                    record_id=job.record_id,
                    locale=job.locale,
                )
                session.add(record)
    except IntegrityError:
        logger.debug("Skipping duplicate notification job", extra={"job": job})
    await _ensure_worker()
    state.job_event.set()
    if metrics is not None:
        await _refresh_persistent_queue_size(metrics)


async def _notification_exists(
    session: AsyncSession,
    job: NotificationJob,
) -> bool:
    """Best-effort idempotency guard based on notification metadata."""

    url: str | None
    notif_type: str | None

    if job.kind == "event":
        url = f"/events/{job.record_id}"
        notif_type = "events.new"
    elif job.kind == "news":
        url = f"/news/{job.record_id}"
        notif_type = "news.new"
    else:  # pragma: no cover - defensive guard
        return False

    if job.record_id <= 0:
        return False

    stmt = (
        select(Notification.id)
        .where(Notification.type == notif_type, Notification.url == url)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _process_job(job: NotificationJob) -> None:
    async with async_session() as session:
        if await _notification_exists(session, job):
            logger.debug("Skipping duplicate notification job", extra={"job": job})
            return
        if job.kind == "event":
            record = await session.get(Event, job.record_id)
            if not record:
                logger.info(
                    "Event %s disappeared before notification dispatch", job.record_id
                )
                return
            await notify_about_event(session, record, locale=job.locale)
        elif job.kind == "news":
            record = await session.get(News, job.record_id)
            if not record:
                logger.info(
                    "News %s disappeared before notification dispatch", job.record_id
                )
                return
            await notify_about_news(session, record, locale=job.locale)
        else:  # pragma: no cover - defensive guard
            logger.warning("Unsupported notification job", extra={"job": job})


async def enqueue_event_notification(
    event_id: int, *, locale: str | None = None
) -> None:
    """Queue an event notification job for asynchronous delivery."""

    await _enqueue_job(NotificationJob(kind="event", record_id=event_id, locale=locale))


async def enqueue_news_notification(news_id: int, *, locale: str | None = None) -> None:
    """Queue a news notification job for asynchronous delivery."""

    await _enqueue_job(NotificationJob(kind="news", record_id=news_id, locale=locale))


async def wait_for_all_jobs(timeout: float | None = None) -> None:
    """Wait until the queue is empty. Intended for tests."""

    state = _get_loop_state()

    async def _wait() -> None:
        if _use_persistent_backend():
            while True:
                pending = await _pending_persistent_jobs()
                if pending == 0 and state.active_jobs == 0:
                    await asyncio.sleep(0)
                    pending = await _pending_persistent_jobs()
                    if pending == 0 and state.active_jobs == 0:
                        return
                await asyncio.sleep(0.01)
        else:
            await state.queue.join()

    if timeout is None:
        await _wait()
        return
    await asyncio.wait_for(_wait(), timeout=timeout)


async def reset_testing_state() -> None:
    """Best-effort helper to clear pending jobs between tests."""

    state = _get_loop_state()
    queue = state.queue
    metrics = _get_metrics()

    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:  # pragma: no cover - defensive guard
            break
        else:
            queue.task_done()
    state.active_jobs = 0
    state.job_event.clear()
    await _clear_persistent_jobs()
    if metrics is not None:
        if _use_persistent_backend():
            await _refresh_persistent_queue_size(metrics)
        else:
            metrics.queue_size.set(queue.qsize())


async def shutdown_notification_queue() -> None:
    """Stop the background worker and drain any pending jobs."""

    state = _get_loop_state()
    queue = state.queue
    worker = state.worker_task
    metrics = _get_metrics()

    if worker is not None:
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        state.worker_task = None

    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:  # pragma: no cover - defensive guard
            break
        else:
            queue.task_done()
    state.active_jobs = 0
    state.job_event.clear()
    await _clear_persistent_jobs()
    if metrics is not None:
        if _use_persistent_backend():
            await _refresh_persistent_queue_size(metrics)
        else:
            metrics.queue_size.set(queue.qsize())


async def _refresh_persistent_queue_size(metrics: NotificationQueueMetrics) -> None:
    """Update queue size metric based on durable backlog."""

    try:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(NotificationQueueJob)
                .where(
                    NotificationQueueJob.claimed_at.is_(None),
                    NotificationQueueJob.dead_lettered.is_(False),
                )
            )
            metrics.queue_size.set(int(result.scalar_one()))
    except Exception:  # pragma: no cover - defensive guard
        logger.exception("Failed to refresh persistent queue size metric")


async def _pending_persistent_jobs() -> int:
    async with async_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(NotificationQueueJob)
            .where(
                NotificationQueueJob.claimed_at.is_(None),
                NotificationQueueJob.dead_lettered.is_(False),
            )
        )
        return int(result.scalar_one())


async def _clear_persistent_jobs() -> None:
    if not _use_persistent_backend():
        return

    try:
        if await _pending_persistent_jobs() == 0:
            return
    except OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        await asyncio.sleep(0.05)

    max_attempts = 5
    delay_seconds = 0.05

    for attempt in range(1, max_attempts + 1):
        async with async_session() as session:
            try:
                await session.execute(delete(NotificationQueueJob))
                await session.commit()
                return
            except OperationalError as exc:
                await session.rollback()
                message = str(exc).lower()
                if "locked" not in message or attempt == max_attempts:
                    raise
                await asyncio.sleep(delay_seconds * attempt)


async def _dequeue_persistent_job(state: _LoopState) -> NotificationJob:
    while True:
        job = await _claim_next_persistent_job()
        if job is not None:
            state.active_jobs += 1
            return job
        state.job_event.clear()
        await state.job_event.wait()


async def _claim_next_persistent_job() -> NotificationJob | None:
    async with async_session() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(NotificationQueueJob)
                .where(
                    NotificationQueueJob.claimed_at.is_(None),
                    NotificationQueueJob.dead_lettered.is_(False),
                    or_(
                        NotificationQueueJob.next_retry_at.is_(None),
                        NotificationQueueJob.next_retry_at <= now,
                    ),
                )
                .order_by(
                    func.coalesce(
                        NotificationQueueJob.next_retry_at,
                        NotificationQueueJob.enqueued_at,
                    ),
                    NotificationQueueJob.enqueued_at,
                    NotificationQueueJob.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.claimed_at = now
            row.attempts = (row.attempts or 0) + 1
            row.next_retry_at = None
            job = NotificationJob(
                kind=cast(JobKind, row.kind),
                record_id=row.record_id,
                locale=row.locale,
                queue_id=row.id,
            )
    metrics = _get_metrics()
    if metrics is not None:
        await _refresh_persistent_queue_size(metrics)
    return job


def _format_job_error(error: BaseException | None) -> str:
    if error is None:
        return "Unknown error"
    message = str(error).strip()
    if not message:
        message = error.__class__.__name__
    if len(message) > 1024:
        return f"{message[:1021]}..."
    return message


async def _acknowledge_persistent_job(
    job: NotificationJob,
    *,
    success: bool,
    error: BaseException | None,
    state: _LoopState,
    metrics: NotificationQueueMetrics | None,
) -> None:
    if job.queue_id is None:
        return
    wake_delay = 0.0
    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(NotificationQueueJob)
                    .where(NotificationQueueJob.id == job.queue_id)
                    .with_for_update()
                )
                record = result.scalar_one_or_none()
                if record is None:
                    return
                if success:
                    await session.delete(record)
                else:
                    error_message = _format_job_error(error)
                    attempts = record.attempts or 0
                    base_delay = max(
                        float(settings.notifications_queue_retry_base_seconds), 0.0
                    )
                    max_attempts = int(settings.notifications_queue_max_attempts)
                    record.last_error = error_message
                    record.claimed_at = None
                    should_dead_letter = max_attempts > 0 and attempts >= max_attempts
                    if should_dead_letter:
                        record.dead_lettered = True
                        record.next_retry_at = None
                        if metrics is not None:
                            metrics.failed_jobs_total.inc()
                        logger.error(
                            "Notification job exhausted retries; moving to dead-letter queue",
                            extra={
                                "job": job,
                                "queue_id": job.queue_id,
                                "attempt": attempts,
                                "max_attempts": max_attempts,
                                "error": error_message,
                            },
                        )
                    else:
                        delay_seconds = base_delay * (2 ** max(attempts - 1, 0))
                        wake_delay = max(delay_seconds, 0.0)
                        next_retry = datetime.now(timezone.utc) + timedelta(
                            seconds=wake_delay
                        )
                        record.dead_lettered = False
                        record.next_retry_at = next_retry
                        logger.warning(
                            "Notification job failed; scheduling retry",
                            extra={
                                "job": job,
                                "queue_id": job.queue_id,
                                "attempt": attempts,
                                "max_attempts": (
                                    max_attempts if max_attempts > 0 else None
                                ),
                                "next_retry_at": next_retry.isoformat(),
                                "error": error_message,
                            },
                        )
    except Exception:
        logger.exception(
            "Failed to acknowledge persistent notification job",
            extra={"job": job, "success": success},
        )
    else:
        if not success:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover - defensive guard
                state.job_event.set()
            else:
                if wake_delay <= 0:
                    state.job_event.set()
                else:
                    loop.call_later(wake_delay, state.job_event.set)
    if metrics is not None:
        await _refresh_persistent_queue_size(metrics)
