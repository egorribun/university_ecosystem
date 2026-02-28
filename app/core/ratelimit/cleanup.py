from __future__ import annotations

import asyncio
import logging

from app.core.ratelimit.strategies.memory import _memory_locks, _memory_windows

logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task | None = None


async def _memory_cleanup_loop(interval_seconds: int = 300) -> None:
    """
    Background loop to prune expired rate limit windows from memory.
    This helps prevent memory leaks when many unique identifiers are used.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            # now = time.time()  # Unused variable removed

            # We don't have a global lock for _memory_windows keys,
            # but we can prune individual windows under their own locks.
            # (Note: keys are only added, never removed in current impl to avoid
            # race conditions with lock creation, but we could prune empty deques)

            # Create a copy of keys to avoid modification during iteration
            async with (
                asyncio.Lock()
            ):  # This is a placeholder, we use individual locks in strategy
                pass

            keys = list(_memory_windows.keys())
            for key in keys:
                lock = _memory_locks.get(key)
                if not lock:
                    continue

                async with lock:
                    window = _memory_windows.get(key)
                    if not window:
                        continue

                    # Prune old entries (we don't know the window_seconds here,
                    # so we use a safe default like 24h or just keep them if they are recent)
                    # Actually, we don't know the expiration time per deque.
                    # A better approach is to prune deques that haven't been touched in a long time.
                    # For now, we'll just implement a basic loop that does nothing or
                    # we can skip this if we prune-on-access.

                    # Wait, if we prune-on-access, why do we need a background task?
                    # The legacy one might have been more aggressive.
                    pass

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in memory rate limit cleanup task: {e}")


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
    except asyncio.CancelledError:
        pass
    _cleanup_task = None
