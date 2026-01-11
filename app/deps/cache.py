from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import logging
import time as time_module
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import orjson
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import record_redis_command

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheEntry:
    etag: str
    payload: Any
    stored_at: float


class BaseCache:
    enabled: bool = False

    async def get(self, key: str) -> CacheEntry | None:
        raise NotImplementedError

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        raise NotImplementedError

    async def invalidate(self, *keys: str) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class NullCache(BaseCache):
    enabled = False

    async def get(self, key: str) -> CacheEntry | None:  # noqa: ARG002
        return None

    async def set(  # noqa: ARG002
        self,
        key: str,
        payload: Any,
        ttl: int | None = None,
    ) -> CacheEntry:
        return CacheEntry(
            etag="",
            payload=payload,
            stored_at=time_module.time(),
        )

    async def invalidate(self, *keys: str) -> None:  # noqa: ARG002
        return None


class MemoryCache(BaseCache):
    enabled = True

    def __init__(self, default_ttl: int = 0):
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._entries: dict[str, tuple[CacheEntry, float]] = {}

    async def get(self, key: str) -> CacheEntry | None:
        now = time_module.time()
        entry, expires_at = self._entries.get(key, (None, 0.0))
        if entry is None:
            return None
        if expires_at and expires_at <= now:
            await self.invalidate(key)
            return None
        return entry

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        stored_at = time_module.time()
        effective_ttl = self._resolve_ttl(ttl)
        expires_at = stored_at + effective_ttl if effective_ttl else 0.0
        entry = CacheEntry(etag=etag, payload=normalized_payload, stored_at=stored_at)
        self._entries[key] = (entry, expires_at)
        return entry

    async def invalidate(self, *keys: str) -> None:
        if not keys:
            return
        for key in keys:
            if "*" in key:
                for stored_key in list(self._entries.keys()):
                    if fnmatch.fnmatch(stored_key, key):
                        self._entries.pop(stored_key, None)
            else:
                self._entries.pop(key, None)

    def _resolve_ttl(self, ttl: int | None) -> int:
        if ttl is None:
            ttl = self._default_ttl
        ttl = int(ttl or 0)
        return ttl if ttl > 0 else 0


class RedisCache(BaseCache):
    enabled = True

    def __init__(self, url: str, default_ttl: int) -> None:
        self._url = url
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._client: Redis | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                # Use robust connection pooling for Redis
                self._client = Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    retry_on_timeout=True,
                    max_connections=getattr(settings, "redis_pool_size", 20),
                )
        return self._client

    async def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        start = time_module.perf_counter()
        success = False
        try:
            await client.aclose()
            success = True
        except (RedisError, OSError):
            logger.debug("Failed to close Redis client", exc_info=True)
        finally:
            record_redis_command(
                "close", time_module.perf_counter() - start, success=success
            )

    async def get(self, key: str) -> CacheEntry | None:
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            raw = await client.get(key)
            if raw is None:
                return None
            parsed = orjson.loads(raw)
            etag = str(parsed.get("etag", ""))
            payload = parsed.get("payload")
            stored_at = float(parsed.get("stored_at") or 0.0)
            if not stored_at:
                stored_at = time_module.time()
            if not etag:
                return None
            success = True
            return CacheEntry(etag=etag, payload=payload, stored_at=stored_at)
        except orjson.JSONDecodeError:
            logger.debug("Invalid cache payload for key %s, dropping", key)
            await self.invalidate(key)
            return None
        except (RedisError, OSError):
            logger.warning("Redis cache get failed for key %s", key, exc_info=True)
            return None
        finally:
            record_redis_command(
                "get", time_module.perf_counter() - start, success=success
            )

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        envelope = orjson.dumps(
            {
                "etag": etag,
                "payload": normalized_payload,
                "stored_at": time_module.time(),
            }
        ).decode("utf-8")
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            expire = self._resolve_ttl(ttl)
            if expire:
                await client.set(key, envelope, ex=expire)
            else:
                await client.set(key, envelope)
            success = True
        except (RedisError, OSError):
            logger.warning("Redis cache set failed for key %s", key, exc_info=True)
        finally:
            record_redis_command(
                "set", time_module.perf_counter() - start, success=success
            )
        return CacheEntry(
            etag=etag, payload=normalized_payload, stored_at=time_module.time()
        )

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(key) for key in keys if key]
        if not filtered:
            return
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()

            # Separate exact keys and patterns
            exact_keys = []
            patterns = []
            for key in filtered:
                if "*" in key:
                    patterns.append(key)
                else:
                    exact_keys.append(key)

            # Delete exact keys
            if exact_keys:
                await client.delete(*exact_keys)

            # Process patterns
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, matches = await client.scan(
                        cursor, match=pattern, count=100
                    )
                    if matches:
                        await client.delete(*matches)
                    if cursor == 0:
                        break
            success = True
        except (RedisError, OSError):
            logger.warning(
                "Redis cache invalidate failed for keys %s", filtered, exc_info=True
            )
        finally:
            record_redis_command(
                "invalidate",
                time_module.perf_counter() - start,
                success=success,
            )

    def _resolve_ttl(self, ttl: int | None) -> int:
        if ttl is None:
            ttl = self._default_ttl
        ttl = int(ttl or 0)
        return ttl if ttl > 0 else 0


class TieredCache(BaseCache):
    enabled = True

    def __init__(self, l1: BaseCache, l2: BaseCache) -> None:
        self.l1 = l1
        self.l2 = l2

    async def get(self, key: str) -> CacheEntry | None:
        # Check L1 first
        entry = await self.l1.get(key)
        if entry is not None:
            return entry

        # Fallback to L2
        entry = await self.l2.get(key)
        if entry is not None:
            # Backfill L1
            await self.l1.set(key, entry.payload)
            return entry

        return None

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        # Set in both layers
        # Note: L1 might have its own default TTL, but we pass the specified one
        entry = await self.l2.set(key, payload, ttl)
        await self.l1.set(key, payload, ttl)
        return entry

    async def invalidate(self, *keys: str) -> None:
        # Invalidate both
        await asyncio.gather(
            self.l1.invalidate(*keys),
            self.l2.invalidate(*keys),
        )

    async def close(self) -> None:
        await asyncio.gather(
            self.l1.close(),
            self.l2.close(),
        )


P = ParamSpec("P")
R = TypeVar("R")


def cached(
    prefix: str | None = None,
    ttl: int | timedelta | None = None,
    l1_ttl: int | timedelta | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to cache function results in the global cache backend.

    Args:
        prefix: Optional prefix for the cache key.
        ttl: Time to live for the cache entry (seconds or timedelta).
        l1_ttl: Optional separate TTL for the L1 (memory) cache.
        key_builder: Optional custom function to build the cache key.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        _prefix = prefix or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cache = get_cache()
            if not cache.enabled:
                return await func(*args, **kwargs)

            # Build key
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                # Basic key building from args/kwargs
                key_parts = [str(arg) for arg in args]
                key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
                key = ":".join(key_parts)

            full_key = f"{_prefix}:{key}"

            # Try get from cache
            entry = await cache.get(full_key)
            if entry is not None:
                return entry.payload

            # Compute and store
            result = await func(*args, **kwargs)

            # Resolve TTL
            seconds = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else ttl

            # Optimization: If we have multiple layers, we can potentially use
            # different TTLs
            # but for now we follow the BaseCache interface.
            # If it's a TieredCache, we could technically override set behavior here
            # but sticking to standard for now.

            await cache.set(full_key, result, ttl=seconds)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


_cache_backend: BaseCache | None = None


def _normalize_payload(payload: Any) -> tuple[Any, bytes]:
    """Normalize payload for caching using orjson for speed."""
    # Use jsonable_encoder to handle Pydantic models, SQLAlchemy models
    jsonable = jsonable_encoder(payload)
    # orjson is 10-15x faster than stdlib json
    serialized = orjson.dumps(
        jsonable,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
    )
    normalized = orjson.loads(serialized) if serialized else jsonable
    return normalized, serialized


def _json_default(value: Any) -> Any:
    """Fallback serializer for types not natively supported."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return str(value)


def create_cache_backend() -> BaseCache:
    if not settings.cache_enabled:
        return NullCache()

    backend = getattr(settings, "cache_backend_normalized", None) or getattr(
        settings, "cache_backend", "redis"
    )
    backend = str(backend).strip().lower()
    ttl = int(getattr(settings, "cache_default_ttl_seconds", 0) or 0)

    if backend == "memory":
        return MemoryCache(default_ttl=ttl)

    if backend == "tiered":
        l1 = MemoryCache(default_ttl=int(getattr(settings, "cache_l1_ttl_seconds", 60)))
        l2_url = (settings.cache_redis_url or "").strip()
        if not l2_url:
            return l1
        l2 = RedisCache(url=l2_url, default_ttl=ttl)
        return TieredCache(l1, l2)

    if backend != "redis":
        return NullCache()

    url = (settings.cache_redis_url or "").strip()
    if not url:
        return NullCache()

    return RedisCache(url=url, default_ttl=ttl)


def get_cache() -> BaseCache:
    global _cache_backend
    if _cache_backend is None:
        _cache_backend = create_cache_backend()
    return _cache_backend


def set_cache_backend(cache: BaseCache | None) -> None:
    global _cache_backend
    _cache_backend = cache


async def shutdown_cache() -> None:
    global _cache_backend
    backend = _cache_backend
    _cache_backend = None
    if backend and isinstance(backend, RedisCache):
        await backend.close()


def format_etag(etag: str) -> str:
    if not etag:
        return etag
    etag = etag.strip()
    if etag.startswith('"') and etag.endswith('"'):
        return etag
    return f'"{etag}"'


def etag_matches(etag: str, header_value: str | None) -> bool:
    if not etag or not header_value:
        return False
    candidate = etag.strip()
    parts = header_value.split(",")
    for part in parts:
        item = part.strip()
        if not item:
            continue
        if item == "*":
            return True
        if item.startswith("W/"):
            item = item[2:].strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1]
        if item == candidate:
            return True
    return False


__all__ = [
    "CacheEntry",
    "BaseCache",
    "NullCache",
    "MemoryCache",
    "RedisCache",
    "TieredCache",
    "cached",
    "create_cache_backend",
    "get_cache",
    "set_cache_backend",
    "shutdown_cache",
    "format_etag",
    "etag_matches",
]
