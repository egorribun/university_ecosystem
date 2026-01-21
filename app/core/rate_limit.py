from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

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

# Memory cleanup configuration
MEMORY_CLEANUP_INTERVAL_SECONDS: int = 300  # 5 minutes
MEMORY_BUCKETS_MAX_ENTRIES: int = 10000  # Maximum entries before forced cleanup
MEMORY_PROGRESSIVE_DELAY_MAX_ENTRIES: int = 5000

_cleanup_task: asyncio.Task[None] | None = None
_cleanup_running: bool = False


def set_rate_limit_client_factory(factory: _RedisFactory | None) -> None:
    global _redis_factory
    if factory is None:
        _redis_factory = _create_redis_pool
    else:
        _redis_factory = factory


@dataclass(frozen=True, slots=True)
class EndpointRateLimit:
    """Configuration for endpoint-specific rate limits."""

    pattern: str  # Path prefix pattern
    limit: int
    window_seconds: int


# Default endpoint-specific rate limits
DEFAULT_ENDPOINT_LIMITS: tuple[EndpointRateLimit, ...] = (
    # Auth endpoints - strictest limits (security-critical)
    EndpointRateLimit("/api/v1/auth/login", 5, 60),
    EndpointRateLimit("/api/v1/auth/register", 5, 60),
    EndpointRateLimit("/api/v1/auth/password-reset", 3, 60),
    EndpointRateLimit("/api/v1/auth/mfa", 5, 60),
    EndpointRateLimit("/api/v1/auth/totp", 5, 60),
    EndpointRateLimit("/token", 5, 60),
    # User profile endpoints - frequently accessed during navigation
    EndpointRateLimit("/api/v1/users/me/avatar", 10, 60),
    EndpointRateLimit("/api/v1/users/me", 120, 60),
    EndpointRateLimit("/api/v1/users/", 60, 60),
    # Notifications - frequently polled during navigation
    EndpointRateLimit("/api/v1/notifications/check-schedule", 60, 60),
    EndpointRateLimit("/api/v1/notifications", 120, 60),
    # Content endpoints - read-heavy, higher limits needed
    # Note: more specific patterns must come first since matching uses startswith
    EndpointRateLimit("/api/v1/news/", 120, 60),
    EndpointRateLimit("/api/v1/events/", 120, 60),
    EndpointRateLimit("/api/v1/chat/", 120, 60),
    EndpointRateLimit("/api/v1/stories", 120, 60),
    EndpointRateLimit("/api/v1/schedule", 120, 60),
    EndpointRateLimit("/api/v1/interactions", 200, 60),
    # Static content endpoints
    EndpointRateLimit("/static/", 300, 60),
    # Admin endpoints
    EndpointRateLimit("/api/v1/admin", 100, 60),
    EndpointRateLimit("/api/internal", 200, 60),
    # WebSocket
    EndpointRateLimit("/ws", 60, 60),
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        redis_url: str | None = None,
        limit: int = 120,
        window_seconds: int = 60,
        enabled: bool = True,
        headers_enabled: bool = True,
        storage_backend: str = "redis",
        endpoint_limits: tuple[EndpointRateLimit, ...] | None = None,
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
        # Per-endpoint rate limits
        self._endpoint_limits = endpoint_limits or DEFAULT_ENDPOINT_LIMITS
        # Each middleware instance should maintain isolated counters when using the
        # in-process memory backend so multiple apps/tests sharing a process do not
        # influence each other.
        self._namespace = f"middleware:{uuid.uuid4().hex}"

    def _get_limits_for_path(self, path: str) -> tuple[int, int, str]:
        """Return (limit, window_seconds, pattern) for a given request path."""
        for endpoint_limit in self._endpoint_limits:
            if path.startswith(endpoint_limit.pattern):
                return (
                    endpoint_limit.limit,
                    endpoint_limit.window_seconds,
                    endpoint_limit.pattern,
                )
        return self._limit, self._window_seconds, "default"

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        method = request.method.upper()
        path = request.url.path or ""

        if method == "HEAD" and self._is_static_like_path(path):
            return Response(status_code=200)

        if not self._enabled or self._should_skip(method, path):
            return await call_next(request)

        # Get endpoint-specific rate limits and the matching pattern
        path_limit, path_window, path_pattern = self._get_limits_for_path(path)

        # Include path pattern in identifier for per-endpoint isolation
        base_identifier = self._build_identifier(request)
        if path_pattern:
            identifier = f"{base_identifier}:{path_pattern}"
        else:
            identifier = base_identifier

        try:
            info = await self._check_limit(identifier, path_limit, path_window)
        except (RedisError, OSError):
            return await call_next(request)

        if not info.allowed:
            retry_after_seconds = max(0, info.retry_after)
            headers = {"Retry-After": str(retry_after_seconds)}
            if self._headers_enabled:
                headers["X-RateLimit-Limit"] = str(path_limit)
                headers["X-RateLimit-Remaining"] = "0"
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers=headers,
            )

        response = await call_next(request)
        if self._headers_enabled:
            response.headers.setdefault("X-RateLimit-Limit", str(path_limit))
            response.headers.setdefault(
                "X-RateLimit-Remaining", str(max(0, info.remaining))
            )
        return response

    async def _check_limit(
        self,
        identifier: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> RateLimitInfo:
        redis_url = self._redis_url if self._storage_backend == "redis" else None
        namespace = self._namespace if self._storage_backend == "memory" else ""
        # Use provided limits or fall back to defaults
        effective_limit = limit if limit is not None else self._limit
        if window_seconds is not None:
            effective_window = window_seconds
        else:
            effective_window = self._window_seconds
        info = await check_rate_limit(
            identifier=identifier,
            namespace=namespace,
            limit=effective_limit,
            window_seconds=effective_window,
            redis_url=redis_url,
        )
        return info

    def _build_identifier(self, request: Request) -> str:
        token = self._extract_bearer_token(request.headers.get("authorization"))
        if token:
            return f"token:{token}"

        cookie_token = self._fingerprint_token(request.cookies.get("access_token"))
        if cookie_token:
            return f"token:{cookie_token}"
        client = request.client
        if client and client.host:
            return f"ip:{client.host}"
        return "ip:unknown"

    @staticmethod
    def _extract_bearer_token(header_value: str | None) -> str | None:
        if not header_value:
            return None
        parts = header_value.strip().split()
        if len(parts) != 2:
            return None
        scheme, token = parts[0].lower(), parts[1].strip()
        if scheme != "bearer" or not token:
            return None
        return RateLimitMiddleware._fingerprint_token(token)

    @staticmethod
    def _fingerprint_token(token: str | None) -> str | None:
        if not token:
            return None
        normalized = token.strip()
        if not normalized:
            return None
        digest = sha256(normalized.encode("utf-8", "ignore")).hexdigest()
        return digest

    def _should_skip(self, method: str, path: str) -> bool:
        """Return ``True`` when the request should bypass rate limiting."""

        if method in {"OPTIONS", "HEAD"}:
            return True

        if path in {"/", "/healthz", "/ready", "/metrics"}:
            return True

        if self._is_static_like_path(path) and method == "GET":
            return True

        return False

    @staticmethod
    def _is_static_like_path(path: str) -> bool:
        if path == "/static" or path.startswith("/static/"):
            return True

        static_like_prefixes = ("/media/", "/storage/", "/assets/")
        return any(path.startswith(prefix) for prefix in static_like_prefixes)


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


# Progressive Delay configuration
PROGRESSIVE_DELAY_STEPS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 20.0, 30.0)
PROGRESSIVE_DELAY_MAX: float = 30.0
PROGRESSIVE_DELAY_TTL: int = 900  # 15 minutes


@dataclass(slots=True)
class ProgressiveDelayInfo:
    """Information about progressive delay state."""

    failures: int
    delay_seconds: float
    should_delay: bool


# In-memory storage for progressive delays (fallback)
_progressive_delay_memory: dict[str, tuple[int, float]] = {}
_progressive_delay_memory_lock = asyncio.Lock()


async def _cleanup_expired_memory_buckets() -> int:
    """
    Remove expired entries from in-memory rate limit buckets.

    Returns:
        Number of buckets cleaned up.
    """
    now = time.time()
    cleaned = 0
    async with _memory_lock:
        expired_keys = []
        for key, bucket in _memory_buckets.items():
            # Remove entries older than the maximum window (1 day)
            max_window = 86400
            bucket[:] = [ts for ts in bucket if now - ts < max_window]
            if not bucket:
                expired_keys.append(key)
        for key in expired_keys:
            del _memory_buckets[key]
            cleaned += 1
    return cleaned


async def _cleanup_expired_progressive_delays(ttl: int = PROGRESSIVE_DELAY_TTL) -> int:
    """
    Remove expired entries from in-memory progressive delay tracker.

    Args:
        ttl: Time-to-live in seconds for entries.

    Returns:
        Number of entries cleaned up.
    """
    now = time.time()
    cleaned = 0
    async with _progressive_delay_memory_lock:
        expired_keys = [
            key
            for key, (_, last_time) in _progressive_delay_memory.items()
            if now - last_time > ttl
        ]
        for key in expired_keys:
            del _progressive_delay_memory[key]
            cleaned += 1
    return cleaned


async def cleanup_all_memory_stores() -> dict[str, int]:
    """
    Cleanup all in-memory stores. Safe to call periodically.

    Returns:
        Dictionary with cleanup statistics.
    """
    buckets_cleaned = await _cleanup_expired_memory_buckets()
    delays_cleaned = await _cleanup_expired_progressive_delays()
    return {
        "rate_limit_buckets_cleaned": buckets_cleaned,
        "progressive_delays_cleaned": delays_cleaned,
        "rate_limit_buckets_remaining": len(_memory_buckets),
        "progressive_delays_remaining": len(_progressive_delay_memory),
    }


async def _periodic_memory_cleanup() -> None:
    """
    Background task that periodically cleans up expired memory entries.
    """
    import logging

    logger = logging.getLogger(__name__)

    while _cleanup_running:
        try:
            await asyncio.sleep(MEMORY_CLEANUP_INTERVAL_SECONDS)
            if not _cleanup_running:
                break

            stats = await cleanup_all_memory_stores()

            # Force cleanup if we exceed max entries
            if len(_memory_buckets) > MEMORY_BUCKETS_MAX_ENTRIES:
                async with _memory_lock:
                    # Keep only the most recent half
                    sorted_keys = sorted(
                        _memory_buckets.keys(),
                        key=lambda k: (
                            max(_memory_buckets[k]) if _memory_buckets[k] else 0
                        ),
                        reverse=True,
                    )
                    keep_count = MEMORY_BUCKETS_MAX_ENTRIES // 2
                    for key in sorted_keys[keep_count:]:
                        del _memory_buckets[key]
                    stats["force_evicted_buckets"] = len(sorted_keys) - keep_count

            if len(_progressive_delay_memory) > MEMORY_PROGRESSIVE_DELAY_MAX_ENTRIES:
                async with _progressive_delay_memory_lock:
                    sorted_keys = sorted(
                        _progressive_delay_memory.keys(),
                        key=lambda k: _progressive_delay_memory[k][1],
                        reverse=True,
                    )
                    keep_count = MEMORY_PROGRESSIVE_DELAY_MAX_ENTRIES // 2
                    for key in sorted_keys[keep_count:]:
                        del _progressive_delay_memory[key]
                    stats["force_evicted_delays"] = len(sorted_keys) - keep_count

            total_cleaned = stats.get("rate_limit_buckets_cleaned", 0) + stats.get(
                "progressive_delays_cleaned", 0
            )
            if total_cleaned > 0:
                logger.debug(
                    "Memory cleanup completed: %s",
                    stats,
                    extra=stats,
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Memory cleanup error: %s", exc)
            await asyncio.sleep(60)  # Backoff on error


def start_memory_cleanup_task() -> asyncio.Task[None] | None:
    """
    Start the background memory cleanup task.

    Returns:
        The cleanup task, or None if already running.
    """
    global _cleanup_task, _cleanup_running

    if _cleanup_task is not None and not _cleanup_task.done():
        return None

    _cleanup_running = True
    _cleanup_task = asyncio.create_task(_periodic_memory_cleanup())
    return _cleanup_task


async def stop_memory_cleanup_task() -> None:
    """
    Stop the background memory cleanup task gracefully.
    """
    global _cleanup_task, _cleanup_running

    _cleanup_running = False
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None


def _calculate_delay(failures: int) -> float:
    """Calculate delay based on failure count."""
    if failures <= 0:
        return 0.0
    index = min(failures - 1, len(PROGRESSIVE_DELAY_STEPS) - 1)
    return min(PROGRESSIVE_DELAY_STEPS[index], PROGRESSIVE_DELAY_MAX)


class ProgressiveDelayTracker:
    """
    Track consecutive auth failures and apply progressive delays.

    This helps mitigate brute-force attacks by adding exponential
    delays after failed authentication attempts.

    Usage:
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        # On failed login
        await tracker.record_failure("ip:192.168.1.1")

        # Before processing login
        delay_info = await tracker.get_delay("ip:192.168.1.1")
        if delay_info.should_delay:
            await asyncio.sleep(delay_info.delay_seconds)

        # On successful login
        await tracker.reset("ip:192.168.1.1")
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        delay_steps: tuple[float, ...] = PROGRESSIVE_DELAY_STEPS,
        max_delay: float = PROGRESSIVE_DELAY_MAX,
        ttl_seconds: int = PROGRESSIVE_DELAY_TTL,
        key_prefix: str = "progressive-delay",
    ) -> None:
        self._redis_url = (redis_url or "").strip()
        self._delay_steps = delay_steps
        self._max_delay = max_delay
        self._ttl = ttl_seconds
        self._key_prefix = key_prefix

    def _make_key(self, identifier: str) -> str:
        """Create Redis key for identifier."""
        return f"{self._key_prefix}:{identifier}"

    async def record_failure(self, identifier: str) -> ProgressiveDelayInfo:
        """
        Record a failed attempt and return current delay info.

        Args:
            identifier: Unique identifier (e.g., "ip:192.168.1.1")

        Returns:
            ProgressiveDelayInfo with updated failure count and delay
        """
        if self._redis_url:
            return await self._record_failure_redis(identifier)
        return await self._record_failure_memory(identifier)

    async def _record_failure_redis(self, identifier: str) -> ProgressiveDelayInfo:
        """Record failure in Redis."""
        try:
            client = await _get_shared_client(self._redis_url)
            key = self._make_key(identifier)

            # Increment failure count
            failures = await client.incr(key)
            await client.expire(key, self._ttl)

            delay = self._calculate_delay(failures)
            return ProgressiveDelayInfo(
                failures=failures,
                delay_seconds=delay,
                should_delay=delay > 0,
            )
        except (RedisError, OSError):
            return await self._record_failure_memory(identifier)

    async def _record_failure_memory(self, identifier: str) -> ProgressiveDelayInfo:
        """Record failure in memory."""
        now = time.time()
        async with _progressive_delay_memory_lock:
            failures, last_time = _progressive_delay_memory.get(identifier, (0, 0.0))
            # Reset if TTL expired
            if now - last_time > self._ttl:
                failures = 0
            failures += 1
            _progressive_delay_memory[identifier] = (failures, now)

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(
            failures=failures,
            delay_seconds=delay,
            should_delay=delay > 0,
        )

    async def get_delay(self, identifier: str) -> ProgressiveDelayInfo:
        """
        Get current delay info without recording a new failure.

        Args:
            identifier: Unique identifier

        Returns:
            ProgressiveDelayInfo with current state
        """
        if self._redis_url:
            return await self._get_delay_redis(identifier)
        return await self._get_delay_memory(identifier)

    async def _get_delay_redis(self, identifier: str) -> ProgressiveDelayInfo:
        """Get delay info from Redis."""
        try:
            client = await _get_shared_client(self._redis_url)
            key = self._make_key(identifier)

            failures_raw = await client.get(key)
            failures = int(failures_raw) if failures_raw else 0

            delay = self._calculate_delay(failures)
            return ProgressiveDelayInfo(
                failures=failures,
                delay_seconds=delay,
                should_delay=delay > 0,
            )
        except (RedisError, OSError, ValueError):
            return await self._get_delay_memory(identifier)

    async def _get_delay_memory(self, identifier: str) -> ProgressiveDelayInfo:
        """Get delay info from memory."""
        now = time.time()
        async with _progressive_delay_memory_lock:
            failures, last_time = _progressive_delay_memory.get(identifier, (0, 0.0))
            if now - last_time > self._ttl:
                failures = 0

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(
            failures=failures,
            delay_seconds=delay,
            should_delay=delay > 0,
        )

    async def reset(self, identifier: str) -> None:
        """
        Reset failure count after successful authentication.

        Args:
            identifier: Unique identifier to reset
        """
        if self._redis_url:
            await self._reset_redis(identifier)
        else:
            await self._reset_memory(identifier)

    async def _reset_redis(self, identifier: str) -> None:
        """Reset in Redis."""
        try:
            client = await _get_shared_client(self._redis_url)
            key = self._make_key(identifier)
            await client.delete(key)
        except (RedisError, OSError):
            await self._reset_memory(identifier)

    async def _reset_memory(self, identifier: str) -> None:
        """Reset in memory."""
        async with _progressive_delay_memory_lock:
            _progressive_delay_memory.pop(identifier, None)

    def _calculate_delay(self, failures: int) -> float:
        """Calculate delay based on failure count."""
        if failures <= 0:
            return 0.0
        index = min(failures - 1, len(self._delay_steps) - 1)
        return min(self._delay_steps[index], self._max_delay)

    async def apply_delay_if_needed(self, identifier: str) -> ProgressiveDelayInfo:
        """
        Check and apply delay if needed. This is a convenience method.

        Args:
            identifier: Unique identifier

        Returns:
            ProgressiveDelayInfo with delay info (after delay applied)
        """
        info = await self.get_delay(identifier)
        if info.should_delay:
            await asyncio.sleep(info.delay_seconds)
        return info


# Global tracker instance (initialized lazily)
_global_progressive_tracker: ProgressiveDelayTracker | None = None


def get_progressive_delay_tracker(
    redis_url: str | None = None,
) -> ProgressiveDelayTracker:
    """Get or create the global progressive delay tracker."""
    global _global_progressive_tracker
    if _global_progressive_tracker is None:
        _global_progressive_tracker = ProgressiveDelayTracker(redis_url=redis_url)
    return _global_progressive_tracker
