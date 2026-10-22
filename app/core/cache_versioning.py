"""Generalized cache version management for list endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.deps.cache import (
    BaseCache,
    RedisCache,
    TieredCache,
    get_cache,
    get_cache_client,
)

logger = get_logger(__name__)


def _shared_version_cache(cache: BaseCache) -> BaseCache:
    # A worker-local L1 cannot hold a shared invalidation generation.
    while isinstance(cache, TieredCache):
        cache = cache.l2 if cache.l2.enabled else cache.l1
    return cache


@dataclass(frozen=True, slots=True)
class CacheVersionManager:
    """Invalidate list payloads with Redis counters or unique shared generations."""

    prefix: str

    @property
    def version_key(self) -> str:
        return f"{self.prefix}:version"

    @property
    def generation_key(self) -> str:
        # NATS KV permits neither colons nor arbitrary prefix characters.
        return "cache-generation." + hashlib.sha256(self.prefix.encode()).hexdigest()

    async def get_version(self, cache: BaseCache | None = None) -> str:
        """Retrieve current version from cache or local fallback."""
        if cache is None:
            cache = get_cache()
        cache = _shared_version_cache(cache)
        if not cache.enabled:
            return "0"

        if isinstance(cache, RedisCache):
            try:
                # MED-W19: use public get_cache_client() instead of private _get_client()
                client = await get_cache_client()
                raw = await client.get(self.version_key)
                if raw is not None:
                    try:
                        return str(int(raw))
                    except (TypeError, ValueError):
                        pass
                return "0"
            except (RedisError, OSError):
                logger.debug("Cache version read failed, returning zero")
            return "0"
        entry = await cache.get(self.generation_key)
        if entry is not None and isinstance(entry.payload, str) and entry.payload:
            return entry.payload
        # Do not store on a miss: a delayed initial reader could overwrite a
        # newer invalidation. A unique uncached token also prevents resurrection
        # of stale payloads when an LRU/TTL evicts the generation entry.
        return uuid4().hex

    async def increment(self, cache: BaseCache | None = None) -> None:
        """Atomically increment version."""
        if cache is None:
            cache = get_cache()
        cache = _shared_version_cache(cache)
        if not cache.enabled:
            return

        if isinstance(cache, RedisCache):
            try:
                # MED-W19: use public get_cache_client() instead of private _get_client()
                client = await get_cache_client()
                if hasattr(client, "incr"):
                    await client.incr(self.version_key)
                else:
                    # Fallback for mocks
                    raw = await client.get(self.version_key)
                    val = int(raw) if raw is not None else 0
                    await client.set(self.version_key, str(val + 1))
            except (RedisError, OSError):
                logger.warning("Failed to increment cache version")
        else:
            # Unique generations avoid a racy read-modify-write increment on
            # backends without INCR. The last completed write invalidates every
            # earlier payload generation, even for concurrent mutations.
            await cache.set(self.generation_key, uuid4().hex, ttl=0)

    async def reset(self, cache: BaseCache | None = None) -> None:
        """Reset a Redis counter, or rotate an opaque backend generation."""
        if cache is None:
            cache = get_cache()
        cache = _shared_version_cache(cache)
        if not cache.enabled:
            return

        if isinstance(cache, RedisCache):
            try:
                # MED-W19: use public get_cache_client() instead of private _get_client()
                client = await get_cache_client()
                await client.set(self.version_key, "0")
            except (RedisError, OSError):
                logger.warning("Failed to reset cache version")
        else:
            await cache.set(self.generation_key, uuid4().hex, ttl=0)

    def build_cache_key(self, *, locale: str, version: str, **params: Any) -> str:
        """Build a deterministic cache key including version and params."""
        signature = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(signature.encode()).hexdigest()
        return f"{self.prefix}:{version}:{locale}:{digest}"


# Global instances as recommended in audit
events_cache_version = CacheVersionManager(prefix="events:list")
news_cache_version = CacheVersionManager(prefix="news:list")
