from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.core.ratelimit.strategies.memory import _memory_windows, _shard_lock

logger = get_logger(__name__)

_cleanup_task: asyncio.Task[None] | None = None


async def _memory_cleanup_loop(interval_seconds: int = 300) -> None:
    """
    Background loop to prune expired rate limit windows from memory.
    This helps prevent memory leaks when many unique identifiers are used.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            import time

            now = time.time()
            # Prune entries where all timestamps are older than this (1 hour default)
            max_age = max(interval_seconds * 12, 3600)
            cutoff = now - max_age

            # Create a copy of keys to avoid modification during iteration
            keys = list(_memory_windows.keys())
            for key in keys:
                lock = _shard_lock(key)
                async with lock:
                    window = _memory_windows.get(key)
                    if not window:
                        continue

                    # Prune old entries from the front of the deque
                    while window and window[0] <= cutoff:
                        window.popleft()

                    # If the deque is now empty, it hasn't been touched in max_age
                    if not window:
                        _memory_windows.pop(key, None)

        except asyncio.CancelledError:
            break
        except Exception as e:  # RZ-22-01-JUSTIFIED: handler-nak — cleanup loop must not crash (reviewed TD-27-04)
            logger.error(
                "Error in memory rate limit cleanup task: %s", e
            )  # LOW-W19: lazy logging


def start_memory_cleanup_task(interval_seconds: int = 300) -> None:
    """Start the background memory cleanup task."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        return

    try:
        loop = asyncio.get_running_loop()
        _cleanup_task = loop.create_task(
            _memory_cleanup_loop(interval_seconds), name="ratelimit_memory_cleanup"
        )
    except RuntimeError:
        # No running loop (e.g. during some tests)
        pass


async def stop_memory_cleanup_task() -> None:
    """Stop the background memory cleanup task."""
    global _cleanup_task
    if _cleanup_task is None:
        return

    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except (asyncio.CancelledError, RuntimeError):
        pass
    _cleanup_task = None
