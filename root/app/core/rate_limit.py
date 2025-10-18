from __future__ import annotations

import asyncio
import math
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_TIME_UNITS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}


def parse_rate_limit(
    value: str | None,
    *,
    fallback: tuple[int, int],
) -> tuple[int, int]:
    """Parse a rate limit definition.

    Args:
        value: A string in the form ``"<count>/<period>"`` or
            ``"<count> per <period>"``.
        fallback: A ``(limit, window_seconds)`` tuple returned when the value is
            missing or invalid.

    Returns:
        A tuple with the allowed request count and the window duration in
        seconds.
    """

    if not value:
        return fallback

    normalized = value.strip().lower()
    if not normalized:
        return fallback

    normalized = normalized.replace("per", "/")
    if "/" in normalized:
        parts = normalized.split("/", 1)
    else:
        parts = normalized.split()

    if len(parts) != 2:
        return fallback

    count_raw, unit_raw = (part.strip() for part in parts)

    try:
        count = int(count_raw)
    except ValueError:
        return fallback

    unit_key = unit_raw.rstrip("s")
    seconds = _TIME_UNITS.get(unit_raw) or _TIME_UNITS.get(unit_key)
    if seconds is None:
        try:
            seconds = int(unit_raw)
        except ValueError:
            return fallback

    if count <= 0 or seconds <= 0:
        return fallback

    return count, seconds


_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
  local retry_after = 0
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  if oldest[2] then
    retry_after = window - (now - tonumber(oldest[2]))
    if retry_after < 0 then
      retry_after = 0
    end
  end
  return {0, 0, retry_after}
end

redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)

local remaining = limit - (count + 1)
if remaining < 0 then
  remaining = 0
end

return {1, remaining, 0}
"""


def _create_redis_pool(url: str) -> Redis:
    return Redis.from_url(
        url, encoding="utf-8", decode_responses=False, health_check_interval=30
    )


_RedisFactory = Callable[[str], Redis]
_redis_factory: _RedisFactory = _create_redis_pool


_shared_clients: dict[str, Redis] = {}
_shared_client_locks: dict[str, asyncio.Lock] = {}
_memory_buckets: dict[str, list[float]] = {}
_memory_lock = asyncio.Lock()


def set_rate_limit_client_factory(factory: Optional[_RedisFactory]) -> None:
    global _redis_factory
    if factory is None:
        _redis_factory = _create_redis_pool
    else:
        _redis_factory = factory


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        redis_url: str | None = None,
        limit: int = 60,
        window_seconds: int = 60,
        enabled: bool = True,
        headers_enabled: bool = True,
        storage_backend: str = "redis",
    ) -> None:
        super().__init__(app)
        backend = (storage_backend or "redis").strip().lower()
        if backend not in {"memory", "redis"}:
            raise ValueError("storage_backend must be either 'memory' or 'redis'")
        self._storage_backend = backend
        self._redis_url = (redis_url or "").strip() if backend == "redis" else ""
        self._limit = max(int(limit), 0)
        self._window_seconds = max(int(window_seconds), 0)
        self._enabled = enabled and self._limit > 0 and self._window_seconds > 0
        if self._storage_backend == "redis":
            self._enabled = self._enabled and bool(self._redis_url)
        self._headers_enabled = headers_enabled

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not self._enabled:
            return await call_next(request)

        identifier = self._build_identifier(request)
        try:
            info = await self._check_limit(identifier)
        except (RedisError, OSError):
            return await call_next(request)

        if not info.allowed:
            retry_after_seconds = max(0, info.retry_after)
            headers = {"Retry-After": str(retry_after_seconds)}
            if self._headers_enabled:
                headers["X-RateLimit-Limit"] = str(self._limit)
                headers["X-RateLimit-Remaining"] = "0"
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers=headers,
            )

        response = await call_next(request)
        if self._headers_enabled:
            response.headers.setdefault("X-RateLimit-Limit", str(self._limit))
            response.headers.setdefault(
                "X-RateLimit-Remaining", str(max(0, info.remaining))
            )
        return response

    async def _check_limit(self, identifier: str) -> RateLimitInfo:
        redis_url = self._redis_url if self._storage_backend == "redis" else None
        info = await check_rate_limit(
            identifier=identifier,
            namespace="",
            limit=self._limit,
            window_seconds=self._window_seconds,
            redis_url=redis_url,
        )
        return info

    def _build_identifier(self, request: Request) -> str:
        auth_header = request.headers.get("authorization")
        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1]:
                return f"token:{parts[1]}"
        client = request.client
        if client and client.host:
            return f"ip:{client.host}"
        return "ip:unknown"

async def _get_shared_client(redis_url: str) -> Redis:
    client = _shared_clients.get(redis_url)
    if client is not None:
        return client
    lock = _shared_client_locks.setdefault(redis_url, asyncio.Lock())
    async with lock:
        client = _shared_clients.get(redis_url)
        if client is None:
            client = _redis_factory(redis_url)
            _shared_clients[redis_url] = client
    return client


def _compose_identifier(namespace: str, identifier: str) -> str:
    ident = identifier.strip() or "unknown"
    ns = namespace.strip()
    return f"{ns}:{ident}" if ns else ident


@dataclass(slots=True)
class RateLimitInfo:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimitExceeded(Exception):
    """Raised when a manual rate limit check fails."""

    def __init__(self, info: RateLimitInfo) -> None:
        super().__init__("Rate limit exceeded")
        self.info = info


async def _memory_rate_limit(
    key: str, limit: int, window_seconds: int
) -> RateLimitInfo:
    if limit <= 0 or window_seconds <= 0:
        return RateLimitInfo(True, max(limit, 0), 0)
    now = time.time()
    cutoff = now - window_seconds
    async with _memory_lock:
        bucket = _memory_buckets.get(key, [])
        bucket = [timestamp for timestamp in bucket if timestamp > cutoff]
        if len(bucket) >= limit:
            retry_after = math.ceil(bucket[0] + window_seconds - now)
            if retry_after < 0:
                retry_after = 0
            _memory_buckets[key] = bucket
            return RateLimitInfo(False, 0, retry_after)
        bucket.append(now)
        _memory_buckets[key] = bucket
        remaining = limit - len(bucket)
    return RateLimitInfo(True, max(0, remaining), 0)


async def _redis_rate_limit_fallback(
    client: Redis,
    redis_key: str,
    window_ms: int,
    limit: int,
    now_ms: int,
    member: str,
) -> RateLimitInfo:
    cutoff = now_ms - window_ms
    await client.zremrangebyscore(redis_key, 0, cutoff)
    count = await client.zcard(redis_key)
    if count >= limit:
        oldest = await client.zrange(redis_key, 0, 0, withscores=True)
        retry_after_ms = 0
        if oldest:
            retry_after_ms = window_ms - (now_ms - int(float(oldest[0][1])))
            if retry_after_ms < 0:
                retry_after_ms = 0
        retry_after = math.ceil(retry_after_ms / 1000)
        return RateLimitInfo(False, 0, max(0, retry_after))
    await client.zadd(redis_key, mapping={member: now_ms})
    await client.pexpire(redis_key, window_ms)
    remaining = limit - (count + 1)
    return RateLimitInfo(True, max(0, remaining), 0)


async def _redis_rate_limit(
    redis_url: str, key: str, limit: int, window_seconds: int
) -> RateLimitInfo:
    if limit <= 0 or window_seconds <= 0:
        return RateLimitInfo(True, max(limit, 0), 0)
    client = await _get_shared_client(redis_url)
    now_ms = int(time.time() * 1000)
    window_ms = max(int(window_seconds * 1000), 1)
    member = f"{now_ms}:{uuid.uuid4().hex}"
    redis_key = f"rate-limit:{key}"
    try:
        result = await client.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            redis_key,
            now_ms,
            window_ms,
            limit,
            member,
        )
    except RedisError as exc:
        if "unknown command" not in str(exc).lower():
            raise
        info = await _redis_rate_limit_fallback(
            client, redis_key, window_ms, limit, now_ms, member
        )
        return info
    allowed = bool(int(result[0]))
    remaining = max(0, int(result[1]))
    retry_after_ms = int(result[2])
    retry_after = math.ceil(retry_after_ms / 1000)
    if retry_after < 0:
        retry_after = 0
    return RateLimitInfo(allowed, remaining, retry_after)


async def check_rate_limit(
    *,
    identifier: str,
    namespace: str = "",
    limit: int,
    window_seconds: int,
    redis_url: str | None = None,
) -> RateLimitInfo:
    """Check a rate limit for an arbitrary identifier."""

    key = _compose_identifier(namespace, identifier)
    redis_uri = (redis_url or "").strip()
    if redis_uri.lower().startswith(("redis://", "rediss://")):
        try:
            return await _redis_rate_limit(redis_uri, key, limit, window_seconds)
        except (RedisError, OSError):
            pass
    return await _memory_rate_limit(key, limit, window_seconds)


async def enforce_rate_limit(
    *,
    identifier: str,
    namespace: str = "",
    limit: int,
    window_seconds: int,
    redis_url: str | None = None,
) -> RateLimitInfo:
    """Enforce a rate limit, raising :class:`RateLimitExceeded` if exceeded."""

    info = await check_rate_limit(
        identifier=identifier,
        namespace=namespace,
        limit=limit,
        window_seconds=window_seconds,
        redis_url=redis_url,
    )
    if not info.allowed:
        raise RateLimitExceeded(info)
    return info
