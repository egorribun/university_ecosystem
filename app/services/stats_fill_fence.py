from __future__ import annotations

import hashlib
import re
import time
from typing import TYPE_CHECKING, Any, cast

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, WatchError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import record_redis_command
from app.deps import cache as cache_module
from app.deps.cache import (
    CacheEntry,
    MemoryCache,
    RedisCache,
    TieredCache,
    _cache_key_fingerprint,
    _normalize_payload,
)

if TYPE_CHECKING:
    from app.deps.cache import BaseCache

logger = get_logger(__name__)
_json: Any = vars(cache_module)["orjson"]
_MARKER = "~stats-fill-v1:"
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")
_MAX_RESERVATION_TTL = 30
_MAX_TTL = 2**31 - 1


def reservation_ttl() -> int:
    """Return the marker lifetime shared by every stats fill."""
    return max(1, min(_MAX_RESERVATION_TTL, settings.stats_cache_ttl_seconds))


def _valid(key: str, token: str, ttl: int, maximum: int) -> bool:
    return (
        isinstance(key, str)
        and bool(key)
        and isinstance(token, str)
        and _TOKEN.fullmatch(token) is not None
        and type(ttl) is int
        and 0 < ttl <= maximum
    )


def _entry(
    payload: object, ttl: int, *, reservation: bool = False
) -> tuple[CacheEntry, str]:
    normalized, serialized = _normalize_payload(payload)
    entry = CacheEntry(
        etag=hashlib.sha256(serialized).hexdigest(),
        payload=normalized,
        # A Redis marker must not be promoted into a TieredCache L1. Its
        # physical lifetime is still controlled by SET EX, not this metadata.
        stored_at=1.0 if reservation else time.time(),
        ttl_seconds=1.0 if reservation else float(ttl),
    )
    raw: bytes = _json.dumps(
        {
            "etag": entry.etag,
            "payload": entry.payload,
            "stored_at": entry.stored_at,
            "ttl_seconds": entry.ttl_seconds,
        }
    )
    return entry, raw.decode("utf-8")


def _redis_backend(cache: BaseCache) -> RedisCache | None:
    if type(cache) is RedisCache:
        return cache
    if type(cache) is TieredCache:
        tiered = cache
        if type(tiered.l1) is MemoryCache and type(tiered.l2) is RedisCache:
            return tiered.l2
    return None


def _watch_transport(exc: WatchError) -> BaseException | None:
    """Follow the visible exception chain without treating contention as failure."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (RedisConnectionError, RedisTimeoutError, OSError)):
            return current
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return None


class StatsFillFence:
    """Fence one stats key; a fresh random token is required for every attempt.

    Memory safety is process-local and requires one event loop. For TieredCache,
    the Redis L2 is authoritative and L1 is populated only by normal read-through.
    Other backends, including NATS KV, are unsupported: callers compute the
    stats without caching them. Successful invalidation is a prerequisite; this
    adapter cannot repair a failed delete.
    """

    def __init__(self, cache: BaseCache) -> None:
        self.cache = cache

    @property
    def supported(self) -> bool:
        """Report whether this backend can fence a fill."""
        return type(self.cache) is MemoryCache or _redis_backend(self.cache) is not None

    async def reserve(self, key: str, token: str, ttl: int) -> bool | None:
        """Return None for unsupported or unknown outcomes, never permission to set."""
        backend = self.cache
        redis_cache = _redis_backend(backend)
        if (type(backend) is not MemoryCache and redis_cache is None) or not _valid(
            key, token, ttl, _MAX_RESERVATION_TTL
        ):
            return None
        marker, raw = _entry(_MARKER + token, ttl, reservation=redis_cache is not None)
        if type(backend) is MemoryCache:
            cache = backend
            now = time.time()
            slot = cache._entries.get(key)
            if slot is not None:
                _, deadline = slot
                if deadline and deadline <= now:
                    cache._entries.pop(key, None)
                else:
                    return False
            cache._store_entry(key, marker, now + ttl)
            return True
        redis_cache = cast("RedisCache", redis_cache)
        start = time.perf_counter()
        success = False
        try:
            client = await redis_cache._get_client()
            reserved = bool(await client.set(key, raw, nx=True, ex=ttl))
            success = True
            return reserved
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis stats reservation failed",
                cache_key_fingerprint=_cache_key_fingerprint(key),
                error_type=type(exc).__name__,
            )
            return None
        finally:
            record_redis_command("set", time.perf_counter() - start, success=success)

    async def complete(
        self, key: str, token: str, payload: object, ttl: int
    ) -> bool | None:
        """Write only if the caller still owns the live marker in the same key."""
        backend = self.cache
        redis_cache = _redis_backend(backend)
        if (
            (type(backend) is not MemoryCache and redis_cache is None)
            or not _valid(key, token, ttl, _MAX_TTL)
            or not isinstance(payload, dict)
        ):
            return None
        value, raw = _entry(payload, ttl)
        marker_tag = _entry(_MARKER + token, 1)[0].etag
        if type(backend) is MemoryCache:
            cache = backend
            now = time.time()
            slot = cache._entries.get(key)
            if slot is None:
                return False
            entry, deadline = slot
            if not deadline or deadline <= now:
                if deadline and deadline <= now:
                    cache._entries.pop(key, None)
                return False
            if entry.payload != _MARKER + token or entry.etag != marker_tag:
                return False
            cache._store_entry(key, value, now + ttl)
            return True
        redis_cache = cast("RedisCache", redis_cache)
        start = time.perf_counter()
        success = False
        try:
            client = await redis_cache._get_client()
            async with client.pipeline(transaction=True) as pipe:
                await pipe.watch(key)
                old = await pipe.get(key)
                if old is None:
                    success = True
                    return False
                try:
                    current: object = _json.loads(old)
                except (ValueError, TypeError):
                    success = True
                    return False
                if (
                    not isinstance(current, dict)
                    or current.get("payload") != _MARKER + token
                    or current.get("etag") != marker_tag
                ):
                    success = True
                    return False
                if await pipe.pttl(key) <= 0:
                    success = True
                    return False
                pipe.multi()
                pipe.set(key, raw, ex=ttl)
                await pipe.execute()
                success = True
                return True
        except WatchError as exc:
            transport = _watch_transport(exc)
            if transport is not None:
                logger.warning(
                    "Redis stats completion failed",
                    cache_key_fingerprint=_cache_key_fingerprint(key),
                    error_type=type(transport).__name__,
                )
                return None
            success = True
            return False
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis stats completion failed",
                cache_key_fingerprint=_cache_key_fingerprint(key),
                error_type=type(exc).__name__,
            )
            return None
        finally:
            record_redis_command("set", time.perf_counter() - start, success=success)
