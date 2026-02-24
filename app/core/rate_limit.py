from __future__ import annotations

import asyncio
import heapq
import hmac
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse, Response

from app.api.validation import raise_http_error
from app.core.config import settings
from app.core.localization import resolve_locale, translate

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
    parts = normalized.split("/", 1) if "/" in normalized else normalized.split()

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


# ---------------------------------------------------------------------------
# Sliding Window Log via Redis Sorted Set (O(log N))
#
# Compared to Fixed Window Counter this algorithm eliminates the "boundary
# burst" vulnerability where an attacker can send 2×limit requests in the
# span of a single millisecond by straddling two consecutive windows.
#
# KEYS[1]  : rate-limit key (namespaced externally)
# ARGV[1]  : limit          (max requests per window)
# ARGV[2]  : now_ms         (current epoch time in milliseconds)
# ARGV[3]  : window_ms      (window size in milliseconds)
#
# Returns: {allowed (0/1), remaining, retry_after_ms}
# ---------------------------------------------------------------------------
_RATE_LIMIT_SCRIPT = """
local key       = KEYS[1]
local limit     = tonumber(ARGV[1])
local now_ms    = tonumber(ARGV[2])
local window_ms = tonumber(ARGV[3])
local cutoff    = now_ms - window_ms

-- 1. Evict requests that have fallen outside the sliding window.
redis.call("ZREMRANGEBYSCORE", key, "-inf", cutoff)

-- 2. Count requests still inside the window.
local current = redis.call("ZCARD", key)

if current >= limit then
    -- Oldest request in the set tells us when the window will free a slot.
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after_ms = 0
    if #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after_ms = math.max(0, (oldest_ts + window_ms) - now_ms)
    end
    return {0, 0, retry_after_ms}
end

-- 3. Record the current request with a unique member to allow multiple
--    requests within the same millisecond (e.g. concurrent load tests).
local member = tostring(now_ms) .. ":" .. tostring(math.random(0, 999999))
redis.call("ZADD", key, now_ms, member)

-- 4. Set the key TTL to window_ms so Redis cleans up idle keys automatically.
redis.call("PEXPIRE", key, window_ms)

local remaining = limit - current - 1
return {1, remaining, 0}
"""


def _create_redis_pool(url: str) -> Redis:
    from typing import cast

    return cast(
        Redis,
        Redis.from_url(
            url, encoding="utf-8", decode_responses=False, health_check_interval=30
        ),
    )


_RedisFactory = Callable[[str], Redis]
_redis_factory: _RedisFactory = _create_redis_pool


_shared_clients: dict[str, Redis] = {}
_shared_client_locks: dict[str, asyncio.Lock] = {}

# Replaced list-based buckets with dictionary: key -> (count, expiry_timestamp)
_memory_counters: dict[str, tuple[int, float]] = {}

# Sharded lock pool: 256 shards reduce contention under high concurrency.
# Each rate-limit key maps to shard = hash(key) & 0xFF so at most 1/256 of
# keys share a lock, allowing ~256× more concurrent in-memory operations
# versus a single global lock.
_LOCK_SHARD_COUNT = 256
_memory_locks: tuple[asyncio.Lock, ...] = tuple(
    asyncio.Lock() for _ in range(_LOCK_SHARD_COUNT)
)

# Priority queue for eviction (expiry_timestamp, key)
_memory_expiry_heap: list[tuple[float, str]] = []


def _shard_lock(key: str) -> asyncio.Lock:
    """Return the lock shard for *key* via bitwise hash bucketing."""
    return _memory_locks[hash(key) & (_LOCK_SHARD_COUNT - 1)]


# Memory cleanup configuration
MEMORY_CLEANUP_INTERVAL_SECONDS: int = 60
MEMORY_COUNTERS_MAX_ENTRIES: int = 50000
_cleanup_task: asyncio.Task[None] | None = None
_cleanup_running: bool = False


def set_rate_limit_client_factory(factory: _RedisFactory | None) -> None:
    global _redis_factory
    _redis_factory = _create_redis_pool if factory is None else factory


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


class RateLimitMiddleware:
    """Pure ASGI rate-limiting middleware.

    Replaces BaseHTTPMiddleware to avoid full response body buffering and
    to preserve streaming responses (SSE, chunked transfer encoding).
    Rate-limit decisions are made on request metadata only (path, headers,
    client IP) — no body is read or buffered.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_url: str | None = None,
        limit: int = 120,
        window_seconds: int = 60,
        enabled: bool = True,
        headers_enabled: bool = True,
        storage_backend: str = "redis",
        endpoint_limits: tuple[EndpointRateLimit, ...] | None = None,
    ) -> None:
        self._app = app
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only rate-limit HTTP requests; pass WebSocket / lifespan through.
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method.upper()
        path = request.url.path or ""

        if method == "HEAD" and self._is_static_like_path(path):
            response = Response(status_code=200)
            await response(scope, receive, send)
            return

        if not self._enabled or self._should_skip(method, path):
            await self._app(scope, receive, send)
            return

        path_limit, path_window, path_pattern = self._get_limits_for_path(path)
        base_identifier = self._build_identifier(request)
        identifier = (
            f"{base_identifier}:{path_pattern}" if path_pattern else base_identifier
        )

        try:
            info = await self._check_limit(identifier, path_limit, path_window)
        except (RedisError, OSError):
            await self._app(scope, receive, send)
            return

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
            response = JSONResponse(
                status_code=429,
                content={"detail": message},
                headers=headers,
            )
            await response(scope, receive, send)
            return

        # Inject rate-limit headers into the downstream response without buffering.
        if self._headers_enabled:
            remaining = str(max(0, info.remaining))
            limit_str = str(path_limit)

            async def send_with_headers(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers_list: list[tuple[bytes, bytes]] = list(
                        message.get("headers", [])
                    )
                    existing_names = {h[0].lower() for h in headers_list}
                    if b"x-ratelimit-limit" not in existing_names:
                        headers_list.append((b"x-ratelimit-limit", limit_str.encode()))
                    if b"x-ratelimit-remaining" not in existing_names:
                        headers_list.append(
                            (b"x-ratelimit-remaining", remaining.encode())
                        )
                    message = {**message, "headers": headers_list}
                await send(message)

            await self._app(scope, receive, send_with_headers)
        else:
            await self._app(scope, receive, send)

    def _get_limits_for_path(self, path: str) -> tuple[int, int, str]:
        for endpoint_limit in self._endpoint_limits:
            if path.startswith(endpoint_limit.pattern):
                return (
                    endpoint_limit.limit,
                    endpoint_limit.window_seconds,
                    endpoint_limit.pattern,
                )
        return self._limit, self._window_seconds, "default"

    async def _check_limit(
        self,
        identifier: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> RateLimitInfo:
        redis_url = self._redis_url if self._storage_backend == "redis" else None
        namespace = self._namespace if self._storage_backend == "memory" else ""
        effective_limit = limit if limit is not None else self._limit
        effective_window = (
            window_seconds if window_seconds is not None else self._window_seconds
        )
        return await check_rate_limit(
            identifier=identifier,
            namespace=namespace,
            limit=effective_limit,
            window_seconds=effective_window,
            redis_url=redis_url,
        )

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

        # A missing secret_key means the application is misconfigured.
        # Falling back to a known string would make HMAC fingerprints predictable.
        if not settings.secret_key:
            raise RuntimeError("SECRET_KEY must be configured for token fingerprinting")
        key = settings.secret_key.encode("utf-8")
        digest = hmac.new(key, normalized.encode("utf-8"), "sha256").hexdigest()
        return digest

    def _should_skip(self, method: str, path: str) -> bool:
        if method in {"OPTIONS", "HEAD"}:
            return True
        if path in {"/", "/healthz", "/ready", "/metrics"}:
            return True
        return bool(self._is_static_like_path(path) and method == "GET")

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


def get_ip_limit_key(ip: str, namespace: str = "") -> str:
    """Helper for tests to generate IP-based limit keys."""
    return _compose_identifier(namespace, f"ip:{ip}")


def get_token_limit_key(token: str, namespace: str = "") -> str:
    """Helper for tests to generate token-based limit keys."""
    return _compose_identifier(namespace, f"token:{token}")


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

    async with _shard_lock(key):
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
        heapq.heappush(_memory_expiry_heap, (expiry, key))
        remaining = limit - count

    return RateLimitInfo(True, max(0, remaining), 0)


async def _redis_rate_limit_fallback(
    client: Redis,
    redis_key: str,
    window_ms: int,
    limit: int,
) -> RateLimitInfo:
    # Atomic fallback: SET NX initialises the key with TTL in one round-trip,
    # then INCR bumps the counter.  Both commands are pipelined so the key
    # can never exist without a TTL (eliminates the TOCTOU race of the old
    # INCR-then-PEXPIRE pattern).
    pipe = client.pipeline(transaction=True)
    pipe.set(redis_key, 0, px=window_ms, nx=True)  # only sets if key is absent
    pipe.incr(redis_key)
    pipe.pttl(redis_key)
    _, current, ttl = await pipe.execute()

    current = int(current)
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
    # Current time in milliseconds — passed as ARGV so the Lua script
    # uses the same clock as the Python process (avoids Redis TIME skew).
    now_ms = int(time.time() * 1000)
    redis_key = f"rate-limit:{key}"

    try:
        from collections.abc import Awaitable
        from typing import Any, cast

        # Sliding Window Log script — returns [allowed (0/1), remaining, retry_after_ms]
        result = await cast(
            Awaitable[Any],
            client.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                redis_key,
                str(limit),
                str(now_ms),
                str(window_ms),
            ),
        )
    except RedisError as exc:
        if "unknown command" not in str(exc).lower():
            raise
        # Fallback: fixed-window pipeline (Redis EVAL unavailable, e.g. Redis Cluster mode)
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
    """Remove expired entries from in-memory rate-limit counters.

    Algorithm (PERF-1: audit 2026-02-24):
    1. Snapshot expired keys from the dict *without* holding any lock —
       a stale snapshot is safe; we re-verify under each shard lock below.
    2. Group keys by shard index to minimise lock acquisitions.
    3. Acquire each affected shard lock exactly once and bulk-delete.

    This replaces the previous 256-sequential-await loop (one ``async with``
    per shard) with at most ``len(expired_keys) // avg_keys_per_shard`` awaits,
    and eliminates the holding of unrelated shard locks during cleanup.
    """
    now = time.time()
    cleaned = 0

    # Step 1: lock-free snapshot — may contain false positives (recently updated
    # keys); those are harmlessly skipped in step 3.
    expired_keys = [
        k
        for k, (_, expiry) in _memory_counters.items()
        if now > expiry + 60  # 60-second grace buffer to avoid thrashing
    ]
    if not expired_keys:
        return 0

    # Step 2: group by shard to minimise lock acquisitions.
    shard_groups: dict[int, list[str]] = {}
    for k in expired_keys:
        shard_idx = hash(k) & (_LOCK_SHARD_COUNT - 1)
        shard_groups.setdefault(shard_idx, []).append(k)

    # Step 3: one lock acquisition per shard that has work to do.
    for shard_idx, keys in shard_groups.items():
        async with _memory_locks[shard_idx]:
            for k in keys:
                entry = _memory_counters.get(k)
                # Re-verify: key may have been refreshed since the snapshot.
                if entry is not None and now > entry[1] + 60:
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
                break  # type: ignore[unreachable]

            await cleanup_all_memory_stores()

            # Priority-Queue based eviction if too big.
            # We pop the oldest items from the heap. Stale entries (keys updated
            # with new expiry) are naturally skipped if their expiry doesn't match.
            # (PERF-2: audit 2026-02-24) Cap heap growth to 3x active counters.
            heap_cap = max(100, len(_memory_counters) * 3)
            if len(_memory_counters) > MEMORY_COUNTERS_MAX_ENTRIES or len(_memory_expiry_heap) > heap_cap:
                evict_count = max(1, int(len(_memory_expiry_heap) * 0.2))
                evicted = 0
                while evicted < evict_count and _memory_expiry_heap:
                    expiry, key = heapq.heappop(_memory_expiry_heap)
                    # Check if this entry is still the current authoritative one
                    current = _memory_counters.get(key)
                    if current is not None and current[1] == expiry:
                        # Only evict if we are over the canonical counter limit.
                        # If we are just over the heap cap, we just discard the
                        # stale heap entry (which happens anyway by popping).
                        if len(_memory_counters) > MEMORY_COUNTERS_MAX_ENTRIES:
                            # Acquire shard lock before deletion
                            async with _shard_lock(key):
                                # Double check after lock
                                actual = _memory_counters.get(key)
                                if actual is not None and actual[1] == expiry:
                                    _memory_counters.pop(key, None)
                                    evicted += 1
                    else:
                        # Stale entry popped from heap — counts as "evicted" from heap
                        # but doesn't increment the 'evicted' counter for DB/memory items.
                        pass

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
    """Cancel the periodic in-memory cleanup task and await its termination."""
    global _cleanup_task, _cleanup_running
    _cleanup_running = False
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await _cleanup_task
    _cleanup_task = None


# --- IP Resolution & Sensitive Route protection ---


def _extract_ip_from_forwarded(forwarded_header: str) -> str | None:
    """Extract IP from RFC 7239 Forwarded header."""
    for segment in forwarded_header.split(","):
        directives = segment.split(";")
        for directive in directives:
            directive = directive.strip()
            if not directive or not directive.lower().startswith("for="):
                continue
            value = directive.split("=", 1)[1].strip().strip('"')
            if not value:
                continue
            if value.startswith("[") and "]" in value:
                value = value[1 : value.index("]")]
            elif value.count(":") == 1 and "]" not in value:
                value = value.split(":", 1)[0]
            return value
    return None


def _normalize_ip(value: str | None) -> str | None:
    """Normalize IP address (handling brackets and ports)."""
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("[") and "]" in normalized:
        normalized = normalized[1 : normalized.index("]")]
    elif normalized.count(":") == 1 and "]" not in normalized:
        normalized = normalized.split(":", 1)[0]
    return normalized or None


def resolve_client_ip(request: Request) -> str:
    """Resolve the real client IP, respecting trusted proxies."""
    client_host = request.client.host if request.client else "unknown"
    normalized_client = _normalize_ip(client_host) or "unknown"
    trusted = {_normalize_ip(proxy) for proxy in settings.trusted_proxies_list}
    trusted.discard(None)

    ip: str | None = None
    if normalized_client in trusted:
        # Check X-Forwarded-For
        xfwd = request.headers.get("X-Forwarded-For")
        if xfwd:
            for part in xfwd.split(","):
                candidate = _normalize_ip(part)
                if candidate:
                    ip = candidate
                    break

        # Check RFC 7239 Forwarded
        if not ip:
            fwd = request.headers.get("Forwarded")
            if fwd:
                ip = _normalize_ip(_extract_ip_from_forwarded(fwd))

    return ip or normalized_client


def sensitive_route_limit(
    limit: int | None = None,
    window_sec: int | None = None,
    *,
    key_prefix: str = "sensitive",
) -> Callable[[Request], Awaitable[None]]:
    """
    FastAPI dependency for sensitive route rate limiting.
    Consolidates logic from legacy utils/ratelimit.py.
    """

    async def dependency(request: Request) -> None:
        # Resolve limit and window from settings or overrides
        default_limit, default_window = parse_rate_limit(
            settings.rate_limit_sensitive_value,
            fallback=(5, 60),
        )
        resolved_limit = limit if limit is not None else default_limit
        resolved_window = window_sec if window_sec is not None else default_window

        if resolved_limit <= 0 or resolved_window <= 0:
            return

        ip = resolve_client_ip(request)
        key = f"{key_prefix}:{ip}:{request.url.path}"
        locale = resolve_locale(request=request)

        try:
            await enforce_rate_limit(
                identifier=key,
                namespace="sensitive",
                limit=resolved_limit,
                window_seconds=resolved_window,
                redis_url=settings.rate_limit_storage_uri,
            )
        except RateLimitExceeded as exc:
            retry_after = max(0, exc.info.retry_after)
            headers = {"Retry-After": str(retry_after)} if retry_after else None
            raise_http_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "errors.rate_limit.generic",
                locale,
                headers=headers,
            )

    return dependency


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
                # Atomic pipeline: INCR and EXPIRE in a single round-trip.
                # Prevents TOCTOU race where a Redis restart between the two
                # calls would leave the counter without a TTL, blocking the
                # user permanently.
                pipe = client.pipeline(transaction=True)
                pipe.incr(key)
                pipe.expire(key, self._ttl)
                results = await pipe.execute()
                failures = int(results[0])
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
            _progressive_delay_memory.pop(key, None)

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
    for lock in _memory_locks:
        async with lock:
            _memory_counters.clear()
    async with _progressive_delay_memory_lock:
        _progressive_delay_memory.clear()


def get_progressive_delay_tracker() -> ProgressiveDelayTracker:
    """FastAPI-injectable factory for ProgressiveDelayTracker.

    Replaces the global singleton pattern, which prevented test isolation.
    Usage in route handlers:
        tracker: ProgressiveDelayTracker = Depends(get_progressive_delay_tracker)

    The tracker is constructed from application settings on each call, but
    since ProgressiveDelayTracker is stateless (state lives in Redis/memory),
    constructing a new instance is cheap and safe.
    """
    try:
        from app.core.config import settings

        redis_url = (
            settings.rate_limit_storage_uri
            if settings.rate_limit_storage_backend == "redis"
            else None
        )
    except ImportError:
        redis_url = None
    return ProgressiveDelayTracker(redis_url=redis_url)


class _Limiter:
    """Shim for legacy tests."""

    def reset(self) -> None:
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            from app.core.rate_limit import clear_all_rate_limit_memory

            task = loop.create_task(clear_all_rate_limit_memory())
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)
        except (RuntimeError, ImportError):
            import asyncio

            from app.core.rate_limit import clear_all_rate_limit_memory

            asyncio.run(clear_all_rate_limit_memory())

    async def check(self, *args, **kwargs) -> None:
        """Mock-ready check method."""
        pass


_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
limiter = _Limiter()
