from __future__ import annotations

import asyncio
import time

from redis.exceptions import RedisError

from app.core.ratelimit.models import ProgressiveDelayInfo
from app.core.ratelimit.strategies.base import get_shared_client

PROGRESSIVE_DELAY_STEPS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 20.0, 30.0)
PROGRESSIVE_DELAY_MAX: float = 30.0
PROGRESSIVE_DELAY_TTL: int = 900  # 15 minutes

_delay_memory: dict[str, tuple[int, float]] = {}
_delay_memory_lock = asyncio.Lock()
# MED-W19: Track last cleanup time to enable periodic pruning of _delay_memory.
_delay_memory_last_cleanup: float = 0.0
_DELAY_MEMORY_CLEANUP_INTERVAL: float = 300.0  # 5 minutes


class ProgressiveDelayTracker:
    def __init__(
        self,
        *,
        redis_url: str | None = None,
        delay_steps: tuple[float, ...] = PROGRESSIVE_DELAY_STEPS,
        max_delay: float = PROGRESSIVE_DELAY_MAX,
        ttl_seconds: int = PROGRESSIVE_DELAY_TTL,
        key_prefix: str = "progressive_delay",
    ) -> None:
        self._redis_url = redis_url
        self._delay_steps = delay_steps
        self._max_delay = max_delay
        self._ttl = ttl_seconds
        self._key_prefix = key_prefix

    def _make_key(self, identifier: str) -> str:
        return f"{self._key_prefix}:{identifier}"

    def _calculate_delay(self, failures: int) -> float:
        if failures <= 0:
            return 0.0
        index = failures - 1
        if index < len(self._delay_steps):
            return self._delay_steps[index]
        return self._max_delay

    async def record_failure(self, identifier: str) -> ProgressiveDelayInfo:
        key = self._make_key(identifier)
        failures = 0

        if self._redis_url:
            try:
                client = await get_shared_client(self._redis_url)
                pipe = client.pipeline(transaction=True)
                pipe.incr(key)
                pipe.expire(key, self._ttl)
                results = await pipe.execute()
                failures = int(results[0])
                delay = self._calculate_delay(failures)
                return ProgressiveDelayInfo(failures, delay, delay > 0)
            except (RedisError, OSError):
                pass

        async with _delay_memory_lock:
            # MED-W19: Periodically prune stale entries to prevent unbounded growth.
            global _delay_memory_last_cleanup
            now_ts = time.time()
            if now_ts - _delay_memory_last_cleanup >= _DELAY_MEMORY_CLEANUP_INTERVAL:
                cutoff_ts = (
                    now_ts - self._ttl
                )  # RZ-33-10: use TTL (900s), not max_delay (30s)
                stale_keys = [
                    k for k, (_, ts) in _delay_memory.items() if ts < cutoff_ts
                ]
                for k in stale_keys:
                    del _delay_memory[k]
                _delay_memory_last_cleanup = now_ts

            count, last_time = _delay_memory.get(key, (0, 0.0))
            if now_ts - last_time > self._ttl:
                count = 0
            count += 1
            _delay_memory[key] = (count, now_ts)
            failures = count

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(failures, delay, delay > 0)

    async def get_delay(self, identifier: str) -> ProgressiveDelayInfo:
        key = self._make_key(identifier)
        failures = 0

        if self._redis_url:
            try:
                client = await get_shared_client(self._redis_url)
                val = await client.get(key)
                if val:
                    failures = int(val)
                delay = self._calculate_delay(failures)
                return ProgressiveDelayInfo(failures, delay, delay > 0)
            except (RedisError, OSError):
                pass

        async with _delay_memory_lock:
            count, last_time = _delay_memory.get(key, (0, 0.0))
            if time.time() - last_time > self._ttl:
                count = 0
            failures = count

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(failures, delay, delay > 0)

    async def reset(self, identifier: str) -> None:
        key = self._make_key(identifier)
        if self._redis_url:
            try:
                client = await get_shared_client(self._redis_url)
                await client.delete(key)
            except (RedisError, OSError):
                pass
        async with _delay_memory_lock:
            _delay_memory.pop(key, None)

    async def apply_delay_if_needed(self, identifier: str) -> ProgressiveDelayInfo:
        info = await self.get_delay(identifier)
        if info.should_delay:
            await asyncio.sleep(info.delay_seconds)
        return info


def clear_delay_memory() -> None:
    _delay_memory.clear()
