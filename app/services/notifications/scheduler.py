"""Notification scheduler functionality.

This module provides the background scheduler for generating and
sending notifications.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.services.notifications.core import async_session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def start_notifications_scheduler(
    *,
    poll_seconds: int = 30,
    window_minutes: int = 6,
    max_backoff_seconds: int = 300,
) -> Callable[[], Awaitable[None]]:
    """Start background notifications scheduler via the worker implementation."""

    from app.workers.notifications import start_notifications_scheduler as _start

    return await _start(
        poll_seconds=poll_seconds,
        window_minutes=window_minutes,
        max_backoff_seconds=max_backoff_seconds,
    )


async def _scheduler_loop(
    poll_seconds: int = 30,
    window_minutes: int = 6,
    *,
    max_backoff_seconds: int = 300,
) -> None:
    """Compatibility wrapper delegating to the worker scheduler loop."""

    from app.workers import notifications as worker_module

    scheduler = worker_module.NotificationsScheduler(
        poll_seconds=poll_seconds,
        window_minutes=window_minutes,
        max_backoff_seconds=max_backoff_seconds,
        metrics=None,
    )

    original_sleep = worker_module.asyncio.sleep
    original_session = worker_module.async_session
    try:
        worker_module.asyncio.sleep = asyncio.sleep
        worker_module.async_session = async_session  # type: ignore[attr-defined]
        try:
            await scheduler.run_forever()
        except asyncio.CancelledError:
            return
    finally:
        worker_module.asyncio.sleep = original_sleep
        worker_module.async_session = original_session
