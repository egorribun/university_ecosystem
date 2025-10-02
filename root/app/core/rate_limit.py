from __future__ import annotations

import asyncio
import math
import time
import uuid
from typing import Callable, Optional

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
    return Redis.from_url(url, encoding="utf-8", decode_responses=False, health_check_interval=30)


_RedisFactory = Callable[[str], Redis]
_redis_factory: _RedisFactory = _create_redis_pool


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
        redis_url: str,
        limit: int = 60,
        window_seconds: int = 60,
        enabled: bool = True,
        headers_enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self._redis_url = redis_url.strip()
        self._limit = max(int(limit), 0)
        self._window_ms = max(int(window_seconds * 1000), 0)
        self._enabled = enabled and bool(self._redis_url) and self._limit > 0 and self._window_ms > 0
        self._headers_enabled = headers_enabled
        self._client: Redis | None = None
        self._client_lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not self._enabled:
            return await call_next(request)

        identifier = self._build_identifier(request)
        try:
            allowed, remaining, retry_after = await self._check_limit(identifier)
        except (RedisError, OSError):
            return await call_next(request)

        if not allowed:
            retry_after_seconds = max(0, math.ceil(retry_after / 1000))
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
            response.headers.setdefault("X-RateLimit-Remaining", str(max(0, remaining)))
        return response

    async def _check_limit(self, identifier: str) -> tuple[bool, int, int]:
        client = await self._get_client()
        now_ms = int(time.time() * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex}"
        key = self._redis_key(identifier)
        try:
            result = await client.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                now_ms,
                self._window_ms,
                self._limit,
                member,
            )
        except RedisError as exc:
            if "unknown command" not in str(exc).lower():
                raise
            return await self._check_limit_fallback(client, key, now_ms, member)
        allowed = bool(int(result[0]))
        remaining = int(result[1])
        retry_after = int(result[2])
        return allowed, remaining, retry_after

    async def _check_limit_fallback(
        self,
        client: Redis,
        key: str,
        now_ms: int,
        member: str,
    ) -> tuple[bool, int, int]:
        cutoff = now_ms - self._window_ms
        await client.zremrangebyscore(key, 0, cutoff)
        count = await client.zcard(key)
        if count >= self._limit:
            oldest = await client.zrange(key, 0, 0, withscores=True)
            retry_after = 0
            if oldest:
                retry_after = self._window_ms - (now_ms - int(float(oldest[0][1])))
                if retry_after < 0:
                    retry_after = 0
            return False, 0, int(retry_after)
        await client.zadd(key, mapping={member: now_ms})
        await client.pexpire(key, self._window_ms)
        remaining = max(0, self._limit - (count + 1))
        return True, remaining, 0

    async def _get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                self._client = _redis_factory(self._redis_url)
        return self._client

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

    def _redis_key(self, identifier: str) -> str:
        return f"rate-limit:{identifier}"
