"""
Multi-layer caching with L1 (in-memory) and L2 (Redis).

Provides a two-tier caching strategy:
- L1: Fast in-memory LRU cache (per-instance)
- L2: Distributed Redis cache (shared across instances)
"""

from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import orjson
from prometheus_client import Counter

from app.core.logging import get_logger

# TD-30-05: Prometheus counters for L1 cache observability.
# Thread-safe by design (atomic inc), feed Grafana dashboards directly.
_L1_CACHE_HITS = Counter("cache_l1_hits_total", "L1 in-memory cache hits")
_L1_CACHE_MISSES = Counter("cache_l1_misses_total", "L1 in-memory cache misses")

logger = get_logger(__name__)


@dataclass
class CacheEntry[T]:
    """Cache entry with value and metadata."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.expires_at


class LRUCache[T]:
    """
    Thread-safe LRU cache for L1 caching.

    Uses OrderedDict for O(1) access and eviction.
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 30.0) -> None:
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds
        """
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        # MOD-20-01 (audit 2026-03-24): threading.Lock protects _hits/_misses
        # and _cache mutations against PEP 703 free-threading.  `+= 1` is NOT
        # atomic under free-threading — two threads can read the same value,
        # increment locally, and write back, losing one increment.
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        """
        Get value from cache.

        Returns None if not found or expired.
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                _L1_CACHE_MISSES.inc()  # TD-30-05
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                _L1_CACHE_MISSES.inc()  # TD-30-05
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            _L1_CACHE_HITS.inc()  # TD-30-05
            return entry.value

    def set(self, key: str, value: T, ttl: float | None = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if not specified)
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Update or insert
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with (
            self._lock
        ):  # RZ-33-03: acquire lock — prevent data race under free-threading
            self._cache.clear()

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidate all keys starting with prefix.

        Returns number of keys invalidated.
        """
        with (
            self._lock
        ):  # RZ-33-03: acquire lock — prevent data race under free-threading
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0-1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


class MultiLayerCache:
    """
    Two-tier cache: L1 (memory) + L2 (Redis).

    Read path: L1 -> L2 -> source
    Write path: Write to both L1 and L2
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l1_ttl: float = 30.0,
        l2_ttl: float = 300.0,
        redis_client: Any | None = None,
    ):
        """
        Initialize multi-layer cache.

        Args:
            l1_max_size: Max entries in L1
            l1_ttl: L1 TTL in seconds
            l2_ttl: L2 TTL in seconds
            redis_client: Optional Redis client for L2
        """
        self.l1 = LRUCache[Any](max_size=l1_max_size, default_ttl=l1_ttl)
        self.l2_ttl = l2_ttl
        self._redis = redis_client

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache (L1 -> L2).
        """
        # Try L1 first
        value = self.l1.get(key)
        if value is not None:
            return value

        # Try L2 if available
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    # PERF-W19-01: deserialize orjson bytes from L2 before returning
                    value = orjson.loads(raw)
                    # Populate L1 from L2
                    self.l1.set(key, value)
                    return value
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as e:  # RZ-22-01: narrowed — Redis errors
                logger.warning("L2 cache get failed: %s", e)
                # PERF-14-04 (audit 2026-03-23): Increment redis_command_errors_total
                # so Alertmanager can fire on sustained L2 degradation.
                # Deferred import avoids circular-import risk (core.metrics imports
                # core.config which imports core.cache transitively on some paths).
                try:
                    from app.core.metrics import record_redis_command

                    record_redis_command("get", 0.0, success=False)
                except Exception:  # nosec B110  # noqa: S110  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
                    pass  # metrics unavailable — never block cache logic

        return None

    async def set(self, key: str, value: Any, l1_ttl: float | None = None) -> None:
        """
        Set value in both L1 and L2.
        """
        # Set in L1
        self.l1.set(key, value, ttl=l1_ttl)

        # Set in L2 if available
        if self._redis is not None:
            try:
                # PERF-W19-01: serialize with orjson so Redis stores valid bytes,
                # not the str() representation of a Python object.
                await self._redis.setex(key, int(self.l2_ttl), orjson.dumps(value))
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as e:  # RZ-22-01: narrowed — Redis errors
                logger.warning("L2 cache set failed: %s", e)
                # PERF-14-04 (audit 2026-03-23): Same pattern as get() above.
                try:
                    from app.core.metrics import record_redis_command

                    record_redis_command("set", 0.0, success=False)
                except Exception:  # nosec B110  # noqa: S110  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
                    pass

    async def delete(self, key: str) -> None:
        """Delete from both layers."""
        self.l1.delete(key)
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as e:  # RZ-22-01: narrowed — Redis errors
                logger.warning("L2 cache delete failed: %s", e)

    async def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidate by prefix in both L1 and L2 layers.

        Returns total number of keys invalidated (L1 + L2).
        """
        count = self.l1.invalidate_prefix(prefix)

        if self._redis is not None:
            try:
                # Use SCAN instead of KEYS for production safety
                cursor = 0
                match_pattern = f"{prefix}*"
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor, match=match_pattern, count=100
                    )
                    if keys:
                        await self._redis.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as e:  # RZ-22-01: narrowed — Redis errors
                logger.warning("L2 cache prefix invalidation failed: %s", e)

        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "l1": self.l1.stats(),
            "l2_available": self._redis is not None,
        }


def _init_caches() -> tuple[
    LRUCache[Any], LRUCache[Any], MultiLayerCache, MultiLayerCache
]:
    """Build global cache singletons from settings (late import avoids circular deps)."""
    from app.core.config import settings

    return (
        LRUCache[Any](
            max_size=settings.cache_user_max_size,
            default_ttl=settings.cache_user_ttl_s,
        ),
        LRUCache[Any](
            max_size=settings.cache_config_max_size,
            default_ttl=settings.cache_config_ttl_s,
        ),
        MultiLayerCache(
            l1_max_size=settings.cache_news_l1_max_size,
            l1_ttl=settings.cache_news_l1_ttl_s,
            l2_ttl=settings.cache_news_l2_ttl_s,
        ),
        MultiLayerCache(
            l1_max_size=settings.cache_schedule_l1_max_size,
            l1_ttl=settings.cache_schedule_l1_ttl_s,
            l2_ttl=settings.cache_schedule_l2_ttl_s,
        ),
    )


# Global L1/L2 cache instances — parameters driven by settings at import time
user_cache, config_cache, news_cache, schedule_cache = _init_caches()


def cached(
    cache_instance: LRUCache[Any] | MultiLayerCache,
    key_builder: Callable[..., str],
    ttl: float | None = None,
    _l1_ttl: float | None = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, Any]]], Callable[..., Coroutine[Any, Any, Any]]
]:
    """AOP decorator to cache asynchronous functions."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_builder(*args, **kwargs)
            # Both LRUCache and MultiLayerCache expose a 'get' method.
            # MultiLayerCache's get is async; LRUCache's is sync.
            if isinstance(cache_instance, MultiLayerCache):
                cached_val = await cache_instance.get(key)
            else:
                cached_val = cache_instance.get(key)

            if cached_val is not None:
                return cached_val

            result = await func(*args, **kwargs)
            if result is not None:
                l1_ttl_val = _l1_ttl if _l1_ttl is not None else ttl
                if isinstance(cache_instance, MultiLayerCache):
                    await cache_instance.set(key, result, l1_ttl=l1_ttl_val)
                else:
                    cache_instance.set(key, result, ttl=l1_ttl_val)
            return result

        return wrapper

    return decorator


__all__ = [
    "CacheEntry",
    "LRUCache",
    "MultiLayerCache",
    "cached",
    "config_cache",
    "news_cache",
    "schedule_cache",
    "user_cache",
]
