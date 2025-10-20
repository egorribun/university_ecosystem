"""In-process queue for dispatching notification jobs asynchronously."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.models import Event, News, Notification
from app.services.notifications import notify_about_event, notify_about_news

logger = logging.getLogger(__name__)


JobKind = Literal["event", "news"]


@dataclass(slots=True, frozen=True)
class NotificationJob:
    """Queued notification delivery request."""

    kind: JobKind
    record_id: int
    locale: str | None


_job_queue: asyncio.Queue[NotificationJob] = asyncio.Queue()
_worker_task: asyncio.Task[None] | None = None
_worker_lock = asyncio.Lock()


async def _ensure_worker() -> None:
    """Ensure that a background worker is running to process queued jobs."""

    global _worker_task

    if _worker_task and not _worker_task.done():
        return

    async with _worker_lock:
        if _worker_task and not _worker_task.done():
            return
        loop = asyncio.get_running_loop()
        _worker_task = loop.create_task(_worker_loop())


async def _worker_loop() -> None:
    """Continuously process notification jobs from the queue."""

    try:
        while True:
            job = await _job_queue.get()
            try:
                await _process_job(job)
            except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
                raise
            except Exception:  # pragma: no cover - defensive guard
                logger.exception("Failed to process notification job", extra={"job": job})
            finally:
                _job_queue.task_done()
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


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


async def enqueue_event_notification(event_id: int, *, locale: str | None = None) -> None:
    """Queue an event notification job for asynchronous delivery."""

    await _job_queue.put(NotificationJob(kind="event", record_id=event_id, locale=locale))
    await _ensure_worker()


async def enqueue_news_notification(news_id: int, *, locale: str | None = None) -> None:
    """Queue a news notification job for asynchronous delivery."""

    await _job_queue.put(NotificationJob(kind="news", record_id=news_id, locale=locale))
    await _ensure_worker()


async def wait_for_all_jobs(timeout: float | None = None) -> None:
    """Wait until the queue is empty. Intended for tests."""

    if timeout is None:
        await _job_queue.join()
        return
    await asyncio.wait_for(_job_queue.join(), timeout=timeout)


async def reset_testing_state() -> None:
    """Best-effort helper to clear pending jobs between tests."""

    while not _job_queue.empty():
        try:
            _job_queue.get_nowait()
        except asyncio.QueueEmpty:  # pragma: no cover - defensive guard
            break
        else:
            _job_queue.task_done()

