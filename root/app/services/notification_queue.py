"""Hybrid queue for dispatching notification jobs asynchronously."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.tasks.notifications import (
    enqueue_event_notification_task,
    enqueue_news_notification_task,
)

logger = logging.getLogger(__name__)


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

    return stop


async def list_dead_lettered_jobs(
    limit: int = 50, offset: int = 0
) -> tuple[list, int]:
    """No-op stub for legacy dead letter queue listing."""
    return [], 0


async def retry_dead_lettered_jobs(job_ids: list[int]) -> int:
    """No-op stub for legacy dead letter queue retry."""
    return 0


async def delete_dead_lettered_jobs(job_ids: list[int]) -> int:
    """No-op stub for legacy dead letter queue deletion."""
    return 0
