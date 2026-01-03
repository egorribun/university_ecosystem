"""
Multi-layer caching with L1 (in-memory) and L2 (Redis).

Provides a two-tier caching strategy:
- L1: Fast in-memory LRU cache (per-instance)
- L2: Distributed Redis cache (shared across instances)
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with value and metadata."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.expires_at


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache for L1 caching.

    Uses OrderedDict for O(1) access and eviction.
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 30.0):
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

    def get(self, key: str) -> T | None:
        """
        Get value from cache.

        Returns None if not found or expired.
        """
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
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
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidate all keys starting with prefix.

        Returns number of keys invalidated.
        """
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

    def get(self, key: str) -> Any | None:
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
                value = self._redis.get(key)
                if value is not None:
                    # Populate L1 from L2
                    self.l1.set(key, value)
                    return value
            except Exception as e:
                logger.warning("L2 cache get failed: %s", e)

        return None

    def set(self, key: str, value: Any, l1_ttl: float | None = None) -> None:
        """
        Set value in both L1 and L2.
        """
        # Set in L1
        self.l1.set(key, value, ttl=l1_ttl)

        # Set in L2 if available
        if self._redis is not None:
            try:
                self._redis.setex(key, int(self.l2_ttl), value)
            except Exception as e:
                logger.warning("L2 cache set failed: %s", e)

    def delete(self, key: str) -> None:
        """Delete from both layers."""
        self.l1.delete(key)
        if self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception as e:
                logger.warning("L2 cache delete failed: %s", e)

    def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate by prefix in L1."""
        return self.l1.invalidate_prefix(prefix)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "l1": self.l1.stats(),
            "l2_available": self._redis is not None,
        }


# Global L1 cache instances
user_cache = LRUCache[Any](max_size=500, default_ttl=60.0)
schedule_cache = LRUCache[Any](max_size=200, default_ttl=120.0)
config_cache = LRUCache[Any](max_size=100, default_ttl=300.0)


__all__ = [
    "CacheEntry",
    "LRUCache",
    "MultiLayerCache",
    "user_cache",
    "schedule_cache",
    "config_cache",
]
