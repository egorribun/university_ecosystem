from __future__ import annotations

import asyncio
import math
import time
from typing import Any, cast

from redis.exceptions import NoScriptError, RedisError, ResponseError

from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies.base import get_shared_client

# PERF-14-01: Cache the Lua script SHA1 so subsequent calls use EVALSHA
# instead of sending the full ~500-byte script on every request.
# Invalidated (set to None) on NoScriptError so it's reloaded after Redis restart.
_RATE_LIMIT_SHA: str | None = None
_SHA_LOCK: asyncio.Lock | None = None  # created lazily to survive event-loop changes


def _get_sha_lock() -> asyncio.Lock:
    global _SHA_LOCK
    if _SHA_LOCK is None:
        _SHA_LOCK = asyncio.Lock()
    return _SHA_LOCK


async def _load_script_sha(client: Any) -> str:
    """Load the Lua script once and cache its SHA1 (PERF-14-01)."""
    global _RATE_LIMIT_SHA
    if _RATE_LIMIT_SHA is not None:
        return _RATE_LIMIT_SHA
    async with _get_sha_lock():
        if _RATE_LIMIT_SHA is None:
            _RATE_LIMIT_SHA = await cast(Any, client).script_load(_RATE_LIMIT_SCRIPT)
        return _RATE_LIMIT_SHA


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
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after_ms = 0
    if #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after_ms = math.max(0, (oldest_ts + window_ms) - now_ms)
    end
    return {0, 0, retry_after_ms}
end

-- 3. Record the current request with a unique member
local member = tostring(now_ms) .. ":" .. tostring(math.random(0, 999999))
redis.call("ZADD", key, now_ms, member)

-- 4. TTL cleanup
redis.call("PEXPIRE", key, window_ms)

local remaining = limit - current - 1
return {1, remaining, 0}
"""


class RedisSlidingWindowStrategy:
    """Redis-backed sliding window rate limit strategy."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitInfo:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitInfo(True, max(limit, 0), 0)

        client = await get_shared_client(self.redis_url)
        window_ms = max(int(window_seconds * 1000), 1)
        now_ms = int(time.time() * 1000)
        redis_key = f"rate-limit:{key}"

        try:
            # PERF-14-01: Prefer EVALSHA (SHA1 lookup, no script transfer) over
            # EVAL (sends full ~500-byte Lua script on every call). Falls back to
            # EVAL on NoScriptError (server restarted / script cache flushed).
            sha = await _load_script_sha(client)
            eval_result = await cast(Any, client).evalsha(
                sha,
                1,
                redis_key,
                str(limit),
                str(now_ms),
                str(window_ms),
            )
            result = cast(list[Any], eval_result)
        except NoScriptError:
            # Script was flushed (SCRIPT FLUSH or server restart) — reload and retry.
            global _RATE_LIMIT_SHA
            _RATE_LIMIT_SHA = None
            eval_result = await cast(Any, client).eval(
                _RATE_LIMIT_SCRIPT,
                1,
                redis_key,
                str(limit),
                str(now_ms),
                str(window_ms),
            )
            result = cast(list[Any], eval_result)
        except RedisError as exc:
            # ResponseError: covers Redis Cluster "unknown command" for EVAL/scripting.
            # All other RedisError subtypes (ConnectionError, TimeoutError, etc.) are re-raised.
            if isinstance(exc, ResponseError):
                err_str = str(exc).lower()
                if (
                    "unknown command" not in err_str
                    and "noscript" not in err_str
                    and not err_str.startswith("err")
                ):
                    raise
            else:
                raise
            # Fallback: fixed-window pipeline (Redis Cluster compatibility)
            return await self._fallback_fixed_window(
                client, redis_key, window_ms, limit
            )

        allowed = bool(result[0])
        remaining = max(0, int(result[1]))
        retry_after_ms = int(result[2])
        retry_after = math.ceil(retry_after_ms / 1000)

        return RateLimitInfo(allowed, remaining, retry_after)

    async def _fallback_fixed_window(
        self, client: Any, redis_key: str, window_ms: int, limit: int
    ) -> RateLimitInfo:
        pipe = client.pipeline(transaction=True)
        pipe.set(redis_key, 0, px=window_ms, nx=True)
        pipe.incr(redis_key)
        pipe.pttl(redis_key)
        _, current, ttl = await pipe.execute()

        current = int(current)
        if current > limit:
            return RateLimitInfo(False, 0, math.ceil(ttl / 1000) if ttl > 0 else 0)

        return RateLimitInfo(True, max(0, limit - current), 0)
