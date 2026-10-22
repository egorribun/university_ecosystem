from __future__ import annotations

import collections
import math
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.utils import compose_identifier

_LOCK_SHARD_COUNT = 256
# The shard locks protect process-wide state shared by every asyncio loop.
# A thread lock is safe across sequential or concurrent loops; asyncio.Lock
# binds to the first loop that contends for it and then fails on another loop.
_memory_locks: list[threading.Lock] = [
    threading.Lock() for _ in range(_LOCK_SHARD_COUNT)
]
_memory_windows: dict[str, collections.deque[float]] = {}


def _shard_lock(key: str) -> threading.Lock:
    idx = hash(key) & (_LOCK_SHARD_COUNT - 1)
    return _memory_locks[idx]


@contextmanager
def _all_memory_locks() -> Iterator[None]:
    """Lock every shard in a stable order for operations on the shared mapping."""
    with ExitStack() as lock_stack:
        for lock in _memory_locks:
            lock_stack.enter_context(lock)
        yield


def _snapshot_memory_window_keys() -> list[str]:
    """Return a stable key snapshot while requests may run on other threads."""
    with _all_memory_locks():
        return list(_memory_windows.keys())


class MemorySlidingWindowStrategy:
    """In-memory sliding window rate limit strategy."""

    def __init__(self, namespace: str = "default") -> None:
        self.namespace = namespace

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitInfo:
        key = compose_identifier(self.namespace, key)
        if limit <= 0 or window_seconds <= 0:
            return RateLimitInfo(True, max(limit, 0), 0)

        now = time.time()
        cutoff = now - window_seconds

        with _shard_lock(key):
            window = _memory_windows.setdefault(key, collections.deque())

            # Evict timestamps that have fallen outside the sliding window.
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= limit:
                retry_after = math.ceil(window[0] + window_seconds - now)
                return RateLimitInfo(False, 0, max(0, retry_after))

            window.append(now)
            remaining = limit - len(window)

        return RateLimitInfo(True, max(0, remaining), 0)


def clear_memory_state() -> None:
    """Clear all in-memory rate limit state (primarily for testing)."""
    with _all_memory_locks():
        _memory_windows.clear()
