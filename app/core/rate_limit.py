from __future__ import annotations

import asyncio
import hmac
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.localization import resolve_locale, translate

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
    """Parse a rate limit definition."""
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


# Fixed Window Counter Script (O(1))
# KEYS[1]: key
# ARGV[1]: limit
# ARGV[2]: window_ms
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local current = redis.call("INCR", key)
if current == 1 then
    redis.call("PEXPIRE", key, window)
end

if current > limit then
    local ttl = redis.call("PTTL", key)
    if ttl < 0 then ttl = 0 end
    return {0, 0, ttl}
end

local remaining = limit - current
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

# Replaced list-based buckets with dictionary: key -> (count, expiry_timestamp)
_memory_counters: dict[str, tuple[int, float]] = {}
_memory_lock = asyncio.Lock()

# Memory cleanup configuration
MEMORY_CLEANUP_INTERVAL_SECONDS: int = 60
MEMORY_COUNTERS_MAX_ENTRIES: int = 50000
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


# Default endpoint-specific rate limits resolved from settings
def get_default_endpoint_limits() -> tuple[EndpointRateLimit, ...]:
    """Helper to build the endpoint limit list from settings."""
    return (
        EndpointRateLimit(
            "/api/v1/auth/login",
            *parse_rate_limit(settings.rate_limit_auth_login, fallback=(5, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/auth/register",
            *parse_rate_limit(settings.rate_limit_auth_register, fallback=(5, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/auth/password-reset",
            *parse_rate_limit(
                settings.rate_limit_auth_password_reset, fallback=(3, 60)
            ),
        ),
        EndpointRateLimit(
            "/api/v1/password/forgot",
            *parse_rate_limit(
                settings.rate_limit_auth_password_reset, fallback=(3, 60)
            ),
        ),
        EndpointRateLimit(
            "/api/v1/password/reset",
            *parse_rate_limit(
                settings.rate_limit_auth_password_reset, fallback=(3, 60)
            ),
        ),
        EndpointRateLimit(
            "/api/v1/auth/mfa",
            *parse_rate_limit(settings.rate_limit_auth_mfa, fallback=(5, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/auth/totp",
            *parse_rate_limit(settings.rate_limit_auth_totp, fallback=(5, 60)),
        ),
        EndpointRateLimit(
            "/token", *parse_rate_limit(settings.rate_limit_auth, fallback=(5, 60))
        ),
        EndpointRateLimit(
            "/api/v1/users/me/avatar",
            *parse_rate_limit(settings.rate_limit_users_avatar, fallback=(10, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/users/me",
            *parse_rate_limit(settings.rate_limit_users_me, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/notifications/check-schedule",
            *parse_rate_limit(
                settings.rate_limit_notifications_check, fallback=(60, 60)
            ),
        ),
        EndpointRateLimit(
            "/api/v1/notifications",
            *parse_rate_limit(settings.rate_limit_notifications, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/news",
            *parse_rate_limit(settings.rate_limit_news, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/events",
            *parse_rate_limit(settings.rate_limit_events, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/chat",
            *parse_rate_limit(settings.rate_limit_chat, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/stories",
            *parse_rate_limit(settings.rate_limit_stories, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/schedule",
            *parse_rate_limit(settings.rate_limit_schedule, fallback=(120, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/interactions",
            *parse_rate_limit(settings.rate_limit_interactions, fallback=(200, 60)),
        ),
        EndpointRateLimit(
            "/static",
            *parse_rate_limit(settings.rate_limit_static, fallback=(300, 60)),
        ),
        EndpointRateLimit(
            "/api/v1/admin",
            *parse_rate_limit(settings.rate_limit_admin, fallback=(100, 60)),
        ),
        EndpointRateLimit(
            "/api/internal",
            *parse_rate_limit(settings.rate_limit_admin, fallback=(200, 60)),
        ),
        EndpointRateLimit(
            "/ws", *parse_rate_limit(settings.rate_limit_websocket, fallback=(60, 60))
        ),
        EndpointRateLimit(
            "/graphql",
            *parse_rate_limit(settings.rate_limit_graphql, fallback=(30, 60)),
        ),
        EndpointRateLimit(
            "/api/graphql",
            *parse_rate_limit(settings.rate_limit_graphql, fallback=(30, 60)),
        ),
    )


DEFAULT_ENDPOINT_LIMITS: tuple[EndpointRateLimit, ...] = get_default_endpoint_limits()


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
        self._endpoint_limits = endpoint_limits or DEFAULT_ENDPOINT_LIMITS
        self._namespace = f"middleware:{uuid.uuid4().hex}"

    def _get_limits_for_path(self, path: str) -> tuple[int, int, str]:
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

        path_limit, path_window, path_pattern = self._get_limits_for_path(path)

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
                headers["X-RateLimit-Reset"] = str(
                    int(time.time()) + retry_after_seconds
                )

            locale = resolve_locale(request=request)
            message = translate("errors.rate_limit.generic", locale=locale)

            return JSONResponse(
                status_code=429,
                content={"detail": message},
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
        from app.core.config import settings

        key = (settings.secret_key or "fallback-key").encode("utf-8")
        digest = hmac.new(key, normalized.encode("utf-8"), "sha256").hexdigest()
        return digest

    def _should_skip(self, method: str, path: str) -> bool:
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
    def __init__(self, info: RateLimitInfo) -> None:
        super().__init__("Rate limit exceeded")
        self.info = info


async def _memory_rate_limit(
    key: str, limit: int, window_seconds: int
) -> RateLimitInfo:
    if limit <= 0 or window_seconds <= 0:
        return RateLimitInfo(True, max(limit, 0), 0)

    now = time.time()

    async with _memory_lock:
        # Check existing counter
        count, expiry = _memory_counters.get(key, (0, 0.0))

        # If expired, reset
        if now > expiry:
            count = 0
            expiry = now + window_seconds

        # Check limit
        if count >= limit:
            retry_after = math.ceil(expiry - now)
            return RateLimitInfo(False, 0, max(0, retry_after))

        # Increment
        count += 1
        _memory_counters[key] = (count, expiry)
        remaining = limit - count

    return RateLimitInfo(True, max(0, remaining), 0)


async def _redis_rate_limit_fallback(
    client: Redis,
    redis_key: str,
    window_ms: int,
    limit: int,
) -> RateLimitInfo:
    # Minimal fallback using Multi/Exec if Lua fails (unlikely in Redis 7)
    # Using simple INCR
    pipe = client.pipeline()
    pipe.incr(redis_key)
    pipe.pttl(redis_key)
    results = await pipe.execute()

    current = results[0]
    ttl = results[1]

    if current == 1:
        await client.pexpire(redis_key, window_ms)
        ttl = window_ms

    if current > limit:
        return RateLimitInfo(False, 0, math.ceil(ttl / 1000) if ttl > 0 else 0)

    return RateLimitInfo(True, max(0, limit - current), 0)


async def _redis_rate_limit(
    redis_url: str, key: str, limit: int, window_seconds: int
) -> RateLimitInfo:
    if limit <= 0 or window_seconds <= 0:
        return RateLimitInfo(True, max(limit, 0), 0)
    client = await _get_shared_client(redis_url)

    window_ms = max(int(window_seconds * 1000), 1)
    redis_key = f"rate-limit:{key}"

    try:
        # returns [allowed (0/1), remaining, retry_after_ms]
        result = await client.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            redis_key,
            limit,
            window_ms,
        )
    except RedisError as exc:
        if "unknown command" not in str(exc).lower():
            raise
        info = await _redis_rate_limit_fallback(client, redis_key, window_ms, limit)
        return info

    allowed = bool(result[0])
    remaining = max(0, int(result[1]))
    retry_after_ms = int(result[2])
    retry_after = math.ceil(retry_after_ms / 1000)

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


# Progressive Delay (Retained for compatibility, but could also be refactored)
# Keeping strict logic separation: RateLimit (Fixed Window) vs Delay (Logic).
# For now, we only cleaned up Rate Limit implementation.


async def _cleanup_expired_memory_buckets() -> int:
    """
    Remove expired entries from in-memory counters.
    """
    now = time.time()
    cleaned = 0
    async with _memory_lock:
        keys_to_delete = [
            k
            for k, (_, expiry) in _memory_counters.items()
            if now > expiry + 60  # Buffer to avoid thrashing
        ]
        for k in keys_to_delete:
            del _memory_counters[k]
            cleaned += 1
    return cleaned


async def cleanup_all_memory_stores() -> dict[str, int]:
    buckets_cleaned = await _cleanup_expired_memory_buckets()
    return {
        "rate_limit_buckets_cleaned": buckets_cleaned,
        "active_counters": len(_memory_counters),
    }


async def _periodic_memory_cleanup() -> None:
    import logging

    logger = logging.getLogger(__name__)

    while _cleanup_running:
        try:
            await asyncio.sleep(MEMORY_CLEANUP_INTERVAL_SECONDS)
            if not _cleanup_running:
                break

            await cleanup_all_memory_stores()

            # Simple LRU-like eviction if too big
            if len(_memory_counters) > MEMORY_COUNTERS_MAX_ENTRIES:
                async with _memory_lock:
                    # Remove random 20%
                    keys = list(_memory_counters.keys())
                    to_remove = keys[: int(len(keys) * 0.2)]
                    for k in to_remove:
                        del _memory_counters[k]

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Memory cleanup error: %s", exc)
            await asyncio.sleep(60)


def start_memory_cleanup_task() -> asyncio.Task[None] | None:
    global _cleanup_task, _cleanup_running
    if _cleanup_task is not None and not _cleanup_task.done():
        return None
    _cleanup_running = True
    _cleanup_task = asyncio.create_task(_periodic_memory_cleanup())
    return _cleanup_task


async def stop_memory_cleanup_task() -> None:
    global _cleanup_task, _cleanup_running
    _cleanup_running = False


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


async def _cleanup_expired_progressive_delays(ttl: int = PROGRESSIVE_DELAY_TTL) -> int:
    """
    Remove expired entries from in-memory progressive delay tracker.
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


def _calculate_delay(failures: int) -> float:
    if failures <= 0:
        return 0.0
    index = failures - 1
    if index < len(PROGRESSIVE_DELAY_STEPS):
        return PROGRESSIVE_DELAY_STEPS[index]
    return PROGRESSIVE_DELAY_MAX


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
                client = await _get_shared_client(self._redis_url)
                failures = await client.incr(key)
                await client.expire(key, self._ttl)
                delay = self._calculate_delay(failures)
                return ProgressiveDelayInfo(failures, delay, delay > 0)
            except (RedisError, OSError):
                pass

        async with _progressive_delay_memory_lock:
            count, last_time = _progressive_delay_memory.get(key, (0, 0.0))
            if time.time() - last_time > self._ttl:
                count = 0
            count += 1
            _progressive_delay_memory[key] = (count, time.time())
            failures = count

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(failures, delay, delay > 0)

    async def get_delay(self, identifier: str) -> ProgressiveDelayInfo:
        key = self._make_key(identifier)
        failures = 0

        if self._redis_url:
            try:
                client = await _get_shared_client(self._redis_url)
                val = await client.get(key)
                if val:
                    failures = int(val)
                delay = self._calculate_delay(failures)
                return ProgressiveDelayInfo(failures, delay, delay > 0)
            except (RedisError, OSError):
                pass

        async with _progressive_delay_memory_lock:
            count, last_time = _progressive_delay_memory.get(key, (0, 0.0))
            if time.time() - last_time > self._ttl:
                count = 0
            failures = count

        delay = self._calculate_delay(failures)
        return ProgressiveDelayInfo(failures, delay, delay > 0)

    async def reset(self, identifier: str) -> None:
        key = self._make_key(identifier)

        if self._redis_url:
            try:
                client = await _get_shared_client(self._redis_url)
                await client.delete(key)
            except (RedisError, OSError):
                pass

        async with _progressive_delay_memory_lock:
            if key in _progressive_delay_memory:
                del _progressive_delay_memory[key]

    async def apply_delay_if_needed(self, identifier: str) -> ProgressiveDelayInfo:
        info = await self.get_delay(identifier)
        if info.should_delay:
            await asyncio.sleep(info.delay_seconds)
        return info


async def clear_all_rate_limit_memory() -> None:
    """
    Clear all in-memory rate limit and progressive delay state.
    Used primarily for testing to ensure isolation.
    """
    async with _memory_lock:
        _memory_counters.clear()
    async with _progressive_delay_memory_lock:
        _progressive_delay_memory.clear()


_tracker_instance: ProgressiveDelayTracker | None = None


def get_progressive_delay_tracker() -> ProgressiveDelayTracker:
    global _tracker_instance
    if _tracker_instance is None:
        try:
            from app.core.config import settings

            redis_url = (
                settings.rate_limit_storage_uri
                if settings.rate_limit_storage_backend == "redis"
                else None
            )
        except ImportError:
            redis_url = None
        _tracker_instance = ProgressiveDelayTracker(redis_url=redis_url)
    return _tracker_instance
