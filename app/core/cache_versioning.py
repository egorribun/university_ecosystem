"""Generalized cache version management for list endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.deps.cache import BaseCache, RedisCache, get_cache, get_cache_client

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CacheVersionManager:
    """Manages cache versions for list-type endpoints with atomic increments."""

    prefix: str

    @property
    def version_key(self) -> str:
        return f"{self.prefix}:version"

    async def get_version(self, cache: BaseCache | None = None) -> str:
        """Retrieve current version from cache or local fallback."""
        if cache is None:
            cache = get_cache()
        if not cache.enabled:
            # Use a global-ish state or an attribute if we can
            # For simplicity in this refactor, we'll keep the caller's local global
            # or use a registry.
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

    async def increment(self, cache: BaseCache | None = None) -> None:
        """Atomically increment version."""
        if cache is None:
            cache = get_cache()
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

    async def reset(self, cache: BaseCache | None = None) -> None:
        """Reset version to zero."""
        if cache is None:
            cache = get_cache()
        if not cache.enabled:
            return

        if isinstance(cache, RedisCache):
            try:
                # MED-W19: use public get_cache_client() instead of private _get_client()
                client = await get_cache_client()
                await client.set(self.version_key, "0")
            except (RedisError, OSError):
                logger.warning("Failed to reset cache version")

    def build_cache_key(self, *, locale: str, version: str, **params: Any) -> str:
        """Build a deterministic cache key including version and params."""
        signature = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(signature.encode()).hexdigest()
        return f"{self.prefix}:{version}:{locale}:{digest}"


# Global instances as recommended in audit
events_cache_version = CacheVersionManager(prefix="events:list")
news_cache_version = CacheVersionManager(prefix="news:list")
