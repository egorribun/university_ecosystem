"""Task registry for background asyncio tasks.

MOD-3 (audit 2026-02-26): The previous pattern stored background tasks in a
plain ``app.state.background_tasks: set()`` and only attached a done-callback
to the outbox task.  Every other task silently swallowed its exceptions — the
set-based approach never awaits tasks on shutdown, causing tasks to be garbage-
collected mid-run.

This module provides ``TaskRegistry`` which:
1. Tracks all managed tasks.
2. Logs exceptions immediately via a done-callback (no silent failures).
3. Cancels and awaits all tasks on shutdown within a configurable timeout.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

_logger = logging.getLogger(__name__)


class TaskRegistry:
    """Lifecycle-managed registry for background asyncio tasks."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        name: str,
    ) -> asyncio.Task[Any]:
        """Schedule *coro* as a background task and register it.

        The task is tracked for clean shutdown and exception logging.
        """
        task: asyncio.Task[Any] = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _logger.error(
                "Background task %r failed unexpectedly",
                task.get_name(),
                exc_info=exc,
            )

    async def shutdown(self, *, timeout: float = 30.0) -> None:
        """Cancel all registered tasks and await their completion.

        Args:
            timeout: Seconds to wait before giving up on graceful shutdown.
        """
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.wait_for(
            asyncio.gather(*self._tasks, return_exceptions=True),
            timeout=timeout,
        )
        self._tasks.clear()
