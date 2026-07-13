from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import inspect
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from app.core.logging import get_logger

try:
    import orjson
except ImportError:
    import json
    from typing import Any

    class OrJsonCompat:
        OPT_SORT_KEYS = 0
        OPT_UTC_Z = 0
        JSONDecodeError = json.JSONDecodeError

        @staticmethod
        def loads(s: str | bytes) -> Any:
            return json.loads(s)

        @staticmethod
        def dumps(v: Any, default: Any = None, _option: int | None = None) -> bytes:
            return json.dumps(v, default=default, sort_keys=True).encode("utf-8")

    orjson = OrJsonCompat()  # type: ignore[assignment]
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import record_redis_command

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


logger = get_logger(__name__)


@dataclass(slots=True)
class CacheEntry:
    etag: str
    payload: Any
    stored_at: float
    ttl_seconds: float = 0.0  # TTL for probabilistic refresh calculation

    def should_refresh_probabilistic(
        self,
        beta: float = 1.0,
    ) -> bool:
        """
        XFetch algorithm for probabilistic early expiration.

        Prevents cache stampede by having some requests refresh
        the cache slightly before expiration.

        Args:
            beta: Scaling factor (higher = earlier refresh probability)

        Returns:
            True if this request should trigger a cache refresh
        """
        import math
        import random

        if self.ttl_seconds <= 0:
            return False

        now = time_module.time()
        age = now - self.stored_at
        remaining = self.ttl_seconds - age

        if remaining <= 0:
            return True  # Already expired

        # XFetch formula: refresh if now - (ttl * beta * log(random)) > expiry
        # Simplified: remaining < -beta * ttl * log(random)
        random_factor = random.random()  # noqa: S311  # nosec B311
        if random_factor == 0:
            random_factor = 1e-10

        threshold = -beta * self.ttl_seconds * math.log(random_factor)
        return remaining < threshold


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

    async def get(self, key: str) -> CacheEntry | None:
        return None

    async def set(
        self,
        _key: str,
        payload: Any,
        _ttl: int | None = None,
    ) -> CacheEntry:
        return CacheEntry(
            etag="",
            payload=payload,
            stored_at=time_module.time(),
        )

    async def invalidate(self, *_keys: str) -> None:
        return None


class MemoryCache(BaseCache):
    enabled = True

    def __init__(self, default_ttl: int = 0, max_size: int = 1000) -> None:
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._max_size = max(int(max_size or 1000), 10)
        from collections import OrderedDict

        self._entries: OrderedDict[str, tuple[CacheEntry, float]] = OrderedDict()

    async def get(self, key: str) -> CacheEntry | None:
        now = time_module.time()
        entry_meta = self._entries.get(key)
        if entry_meta is None:
            return None

        entry, expires_at = entry_meta
        if expires_at and expires_at <= now:
            self._entries.pop(key, None)
            return None

        # Move to end (most recently used)
        self._entries.move_to_end(key)
        return entry

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        stored_at = time_module.time()
        effective_ttl = self._resolve_ttl(ttl)
        expires_at = stored_at + effective_ttl if effective_ttl else 0.0
        entry = CacheEntry(
            etag=etag,
            payload=normalized_payload,
            stored_at=stored_at,
            ttl_seconds=float(effective_ttl),
        )

        # Evict oldest if full
        if key not in self._entries and len(self._entries) >= self._max_size:
            self._entries.popitem(last=False)

        self._entries[key] = (entry, expires_at)
        self._entries.move_to_end(key)
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
        self._client: Redis[Any] | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> Redis[Any]:
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
        return cast("Redis[Any]", self._client)

    async def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        start = time_module.perf_counter()
        success = False
        try:
            if hasattr(client, "aclose") and inspect.iscoroutinefunction(client.aclose):
                await client.aclose()
            elif hasattr(client, "close"):
                res = client.close()
                if inspect.isawaitable(res):
                    await res
            success = True
        except RedisError, OSError, AttributeError:  # RZ-28-01
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
            ttl_seconds = float(parsed.get("ttl_seconds") or 0.0)
            if not stored_at:
                stored_at = time_module.time()
            if not etag:
                return None
            success = True
            return CacheEntry(
                etag=etag,
                payload=payload,
                stored_at=stored_at,
                ttl_seconds=ttl_seconds,
            )
        except orjson.JSONDecodeError:
            logger.debug("Invalid cache payload for key %s, dropping", key)
            await self.invalidate(key)
            return None
        except RedisError, OSError:  # RZ-28-01
            logger.warning("Redis cache get failed for key %s", key, exc_info=True)
            return None
        finally:
            record_redis_command(
                "get", time_module.perf_counter() - start, success=success
            )

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        effective_ttl = self._resolve_ttl(ttl)
        stored_at = time_module.time()
        envelope = orjson.dumps(
            {
                "etag": etag,
                "payload": normalized_payload,
                "stored_at": stored_at,
                "ttl_seconds": float(effective_ttl),
            }
        ).decode("utf-8")
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            if effective_ttl:
                await client.set(key, envelope, ex=effective_ttl)
            else:
                await client.set(key, envelope)
            success = True
        except RedisError, OSError:  # RZ-28-01
            logger.warning("Redis cache set failed for key %s", key, exc_info=True)
        finally:
            record_redis_command(
                "set", time_module.perf_counter() - start, success=success
            )
        return CacheEntry(
            etag=etag,
            payload=normalized_payload,
            stored_at=stored_at,
            ttl_seconds=float(effective_ttl),
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
        except RedisError, OSError:  # RZ-28-01
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


class RedisClusterCache(BaseCache):
    """Redis Cluster cache backend for horizontal scaling."""

    enabled = True

    def __init__(self, url: str, default_ttl: int) -> None:
        self._url = url
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._client: Any = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                try:
                    from redis.asyncio.cluster import RedisCluster

                    self._client = RedisCluster.from_url(
                        self._url,
                        decode_responses=True,
                    )
                except ImportError:
                    logger.warning("redis cluster not available, fallback to single")
                    self._client = Redis.from_url(
                        self._url,
                        decode_responses=True,
                    )
        return self._client

    async def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        start = time_module.perf_counter()
        success = False
        try:
            if hasattr(client, "aclose"):
                await client.aclose()
            elif hasattr(client, "close"):
                await client.close()
            success = True
        except RedisError, OSError, AttributeError:  # RZ-28-01
            logger.debug("Failed to close Redis cluster client", exc_info=True)
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
            success = True
            return CacheEntry(
                etag=str(parsed.get("etag", "")),
                payload=parsed.get("payload"),
                stored_at=float(parsed.get("stored_at") or time_module.time()),
                ttl_seconds=float(parsed.get("ttl_seconds") or 0.0),
            )
        except orjson.JSONDecodeError:
            logger.debug("Invalid cache payload in cluster for key %s", key)
            return None
        except RedisError, OSError:  # RZ-28-01
            logger.warning("Redis cluster get failed for key %s", key, exc_info=True)
            return None
        finally:
            record_redis_command(
                "get", time_module.perf_counter() - start, success=success
            )

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        effective_ttl = self._resolve_ttl(ttl)
        stored_at = time_module.time()
        envelope = orjson.dumps(
            {
                "etag": etag,
                "payload": normalized,
                "stored_at": stored_at,
                "ttl_seconds": float(effective_ttl),
            }
        ).decode("utf-8")
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            if effective_ttl:
                await client.set(key, envelope, ex=effective_ttl)
            else:
                await client.set(key, envelope)
            success = True
        except RedisError, OSError:  # RZ-28-01
            logger.warning("Redis cluster set failed for key %s", key, exc_info=True)
        finally:
            record_redis_command(
                "set", time_module.perf_counter() - start, success=success
            )
        return CacheEntry(
            etag=etag,
            payload=normalized,
            stored_at=stored_at,
            ttl_seconds=float(effective_ttl),
        )

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(k) for k in keys if k]
        if not filtered:
            return
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()

            # TD-33-10: Separate exact keys and patterns (same as RedisCache).
            exact_keys = []
            patterns = []
            for key in filtered:
                if "*" in key:
                    patterns.append(key)
                else:
                    exact_keys.append(key)

            if exact_keys:
                await client.delete(*exact_keys)

            # Process patterns via SCAN — works on both single-node and cluster.
            for pattern in patterns:
                cursor: int = 0
                while True:
                    cursor, matches = await client.scan(
                        cursor, match=pattern, count=100
                    )
                    if matches:
                        await client.delete(*matches)
                    if cursor == 0:
                        break
            success = True
        except RedisError, OSError:  # RZ-28-01
            logger.warning(
                "Redis cluster invalidate failed for keys %s", filtered, exc_info=True
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


class NatsKVCache(BaseCache):
    """NATS Key-Value store cache backend."""

    enabled = True

    def __init__(self, bucket: str, default_ttl: int) -> None:
        self._bucket_name = bucket
        self._default_ttl = default_ttl
        self._kv: Any = None
        self._lock = asyncio.Lock()

    async def _get_kv(self) -> Any:
        if self._kv is not None:
            return self._kv
        async with self._lock:
            if self._kv is None:
                from app.core.nats_broker import broker as global_broker

                if not global_broker.is_connected:
                    await global_broker.connect()

                js = global_broker.js
                if js is None:
                    raise RuntimeError("NATS JetStream not initialized")
                self._kv = await js.key_value(bucket=self._bucket_name)
        return self._kv

    async def get(self, key: str) -> CacheEntry | None:
        try:
            kv = await self._get_kv()
            entry = await kv.get(key)
            if entry is None:
                return None
            parsed = orjson.loads(entry.value)
            return CacheEntry(
                etag=str(parsed.get("etag", "")),
                payload=parsed.get("payload"),
                stored_at=float(parsed.get("stored_at") or time_module.time()),
                ttl_seconds=float(parsed.get("ttl_seconds") or 0.0),
            )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — NATS KV get failures return None (cache miss) (reviewed TD-27-04)
            # nats.js.errors.KeyNotFoundError is common on cache miss if bucket exists
            # but key doesn't.
            logger.debug("NATS KV get failed for key %s: %s", key, exc)
            return None

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        effective_ttl = self._resolve_ttl(ttl)
        stored_at = time_module.time()
        envelope = orjson.dumps(
            {
                "etag": etag,
                "payload": normalized,
                "stored_at": stored_at,
                "ttl_seconds": float(effective_ttl),
            }
        )
        try:
            kv = await self._get_kv()
            await kv.put(key, envelope)
        except (
            OSError,
            ConnectionError,
        ) as exc:  # RZ-22-01: narrowed — NATS KV write errors
            logger.warning("NATS KV set failed for key %s: %s", key, exc)
        return CacheEntry(
            etag=etag,
            payload=normalized,
            stored_at=stored_at,
            ttl_seconds=float(effective_ttl),
        )

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(k) for k in keys if k]
        if not filtered:
            return
        try:
            kv = await self._get_kv()
            for key in filtered:
                if "*" in key:
                    # NATS KV doesn't support pattern deletion easily without listing.
                    # For simplicity in this migration, we only support exact keys.
                    # If patterns are needed, we'd need to use kv.keys() and filter.
                    keys_to_del = await kv.keys()
                    for k in keys_to_del:
                        if fnmatch.fnmatch(k, key):
                            await kv.delete(k)
                else:
                    await kv.delete(key)
        except (
            OSError,
            ConnectionError,
        ) as exc:  # RZ-22-01: narrowed — NATS KV invalidation errors
            logger.warning("NATS KV invalidate failed: %s", exc)

    async def close(self) -> None:
        self._kv = None

    def _resolve_ttl(self, ttl: int | None) -> int:
        if ttl is None:
            ttl = self._default_ttl
        return max(int(ttl or 0), 0)


# Cache key versioning for safe invalidation
_cache_key_version: int = 1


def set_cache_key_version(version: int) -> None:
    """Set global cache key version for safe invalidation."""
    global _cache_key_version
    _cache_key_version = version


def get_cache_key_version() -> int:
    """Get current cache key version."""
    return _cache_key_version


def versioned_key(key: str) -> str:
    """Create a versioned cache key for safe invalidation."""
    return f"v{_cache_key_version}:{key}"


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
    _l1_ttl: int | timedelta | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to cache function results in the global cache backend.

    Args:
        prefix: Optional prefix for the cache key.
        ttl: Time to live for the cache entry (seconds or timedelta).
        l1_ttl: Optional separate TTL for the L1 (memory) cache.
        key_builder: Optional custom function to build the cache key.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
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
                # Skip `self` for bound methods to avoid unstable str(self) in keys
                _args: tuple[object, ...] = args
                if _args and hasattr(_args[0], "__dict__"):
                    _args = _args[1:]
                key_parts = [str(arg) for arg in _args]
                key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
                key = ":".join(key_parts)

            full_key = f"{_prefix}:{key}"

            # Try get from cache
            entry = await cache.get(full_key)
            if entry is not None:
                return cast(R, entry.payload)

            # Compute and store
            result = await func(*args, **kwargs)

            # Resolve TTL
            seconds = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else ttl

            # TD-33-09: If TieredCache and _l1_ttl specified, set L1 with
            # separate TTL for shorter in-memory retention.
            l1_secs = (
                int(_l1_ttl.total_seconds())
                if isinstance(_l1_ttl, timedelta)
                else _l1_ttl
            )
            if l1_secs and isinstance(cache, TieredCache):
                await cache.l2.set(full_key, result, ttl=seconds)
                await cache.l1.set(full_key, result, ttl=l1_secs)
            else:
                await cache.set(full_key, result, ttl=seconds)
            return result

        return wrapper

    return decorator


def stale_while_revalidate(
    prefix: str | None = None,
    ttl: int | timedelta | None = None,
    stale_ttl: int | timedelta | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator implementing stale-while-revalidate pattern.

    Returns stale data immediately while revalidating in background.
    Useful for schedule data and other frequently accessed content.

    Args:
        prefix: Cache key prefix
        ttl: Fresh TTL - how long data is considered fresh
        stale_ttl: Total TTL including stale period (must be > ttl)
        key_builder: Custom key builder function
    """
    fresh_seconds = (
        int(ttl.total_seconds()) if isinstance(ttl, timedelta) else (ttl or 60)
    )
    total_seconds = (
        int(stale_ttl.total_seconds())
        if isinstance(stale_ttl, timedelta)
        else (stale_ttl or fresh_seconds * 2)
    )

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _prefix = prefix or func.__name__
        _revalidation_lock: dict[str, bool] = {}

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cache = get_cache()
            if not cache.enabled:
                return await func(*args, **kwargs)

            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                key_parts = [str(arg) for arg in args]
                key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
                key = ":".join(key_parts)

            full_key = f"{_prefix}:{key}"
            entry = await cache.get(full_key)

            if entry is not None:
                age = time_module.time() - entry.stored_at
                is_stale = age > fresh_seconds

                if is_stale and full_key not in _revalidation_lock:
                    # Mark as revalidating and refresh in background
                    _revalidation_lock[full_key] = True

                    async def revalidate() -> None:
                        try:
                            result = await func(*args, **kwargs)
                            await cache.set(full_key, result, ttl=total_seconds)
                        finally:
                            _revalidation_lock.pop(full_key, None)

                    # Prevent garbage collection of fire-and-forget task
                    task = asyncio.create_task(revalidate())
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)

                # Return stale data immediately
                return cast(R, entry.payload)

            # Cache miss - compute and store
            result = await func(*args, **kwargs)
            await cache.set(full_key, result, ttl=total_seconds)
            return result

        return wrapper

    return decorator


_cache_backend: BaseCache | None = None
_cache_backend_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01
_background_tasks: set[asyncio.Task[Any]] = set()


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

    if backend == "redis":
        url = (settings.cache_redis_url or "").strip()
        if not url:
            return NullCache()
        return RedisCache(url=url, default_ttl=ttl)

    if backend == "nats":
        bucket = getattr(settings, "cache_nats_bucket", "ue_cache")
        return NatsKVCache(bucket=bucket, default_ttl=ttl)

    return NullCache()


def get_cache() -> BaseCache:
    global _cache_backend
    if _cache_backend is not None:  # RZ-33-29: fast path — no lock after init
        return _cache_backend
    with _cache_backend_lock:  # RZ-33-29: slow path — double-checked locking
        if _cache_backend is None:
            _cache_backend = create_cache_backend()
        return _cache_backend


def set_cache_backend(cache: BaseCache | None) -> None:
    global _cache_backend
    _cache_backend = cache


async def get_cache_client() -> Redis[Any]:
    """Get the underlying Redis client from the global cache backend.

    Used for features not exposed by BaseCache, like distributed locks. (RZ-1)
    """
    cache = get_cache()
    if hasattr(cache, "_get_client"):
        return cast("Redis[Any]", await cast(Any, cache)._get_client())
    if hasattr(cache, "l2") and hasattr(cast(Any, cache).l2, "_get_client"):
        return cast("Redis[Any]", await cast(Any, cache.l2)._get_client())
    raise RuntimeError(
        f"Cache backend {type(cache)} does not support direct Redis client access."
    )


async def shutdown_cache() -> None:
    global _cache_backend
    backend = _cache_backend
    _cache_backend = None
    if backend is None:
        return
    # RedisCache, RedisClusterCache, NatsKVCache — anything with .close()
    if hasattr(backend, "close"):
        await backend.close()
    # TieredCache: close the L2 layer if it exposes .close()
    if hasattr(backend, "l2") and hasattr(backend.l2, "close"):
        await backend.l2.close()


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
    "BaseCache",
    "CacheEntry",
    "MemoryCache",
    "NatsKVCache",
    "NullCache",
    "RedisCache",
    "TieredCache",
    "cached",
    "create_cache_backend",
    "etag_matches",
    "format_etag",
    "get_cache",
    "set_cache_backend",
    "shutdown_cache",
]
