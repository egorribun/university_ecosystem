from __future__ import annotations

import asyncio
import collections
import math
import time

from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.utils import compose_identifier

_LOCK_SHARD_COUNT = 256
# MED-W19: Lazy-init asyncio.Lock objects instead of creating them at module
# import time.  asyncio.Lock() must be created inside a running event loop;
# instantiating them at import time causes DeprecationWarning in Python 3.10+
# and a RuntimeError in Python 3.12+ when no event loop is running.
_memory_locks: list[asyncio.Lock | None] = [None] * _LOCK_SHARD_COUNT
_memory_windows: dict[str, collections.deque[float]] = {}


def _shard_lock(key: str) -> asyncio.Lock:
    idx = hash(key) & (_LOCK_SHARD_COUNT - 1)
    lock = _memory_locks[idx]
    if lock is None:
        lock = asyncio.Lock()
        _memory_locks[idx] = lock
    return lock


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

        async with _shard_lock(key):
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
    _memory_windows.clear()
