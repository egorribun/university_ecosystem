from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.rate_limit import (
    RateLimitExceeded,
    enforce_rate_limit,
    parse_rate_limit,
)
from app.localization import resolve_locale, translate

DEFAULT_LIMIT = 5
DEFAULT_WINDOW_SECONDS = 60

_TIME_UNITS = {
    "s": 1,
    "sec": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}


class MemoryLimiter:
    def __init__(self) -> None:
        self.bucket: dict[str, list[float]] = {}

    def check(self, key: str, limit: int, window_sec: int, *, message: str) -> None:
        if limit <= 0 or window_sec <= 0:
            return
        now = time.time()
        cutoff = now - window_sec
        arr = [
            timestamp for timestamp in self.bucket.get(key, []) if timestamp > cutoff
        ]
        if len(arr) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=message,
            )
        arr.append(now)
        self.bucket[key] = arr

    def reset(self) -> None:
        self.bucket.clear()


limiter = MemoryLimiter()


def _resolve_redis_url() -> str | None:
    backend = settings.rate_limit_storage_backend.strip().lower()
    url = settings.rate_limit_storage_uri.strip()
    if backend == "redis" and url.lower().startswith(("redis://", "rediss://")):
        return url
    return None


def _resolve_limits(
    override_limit: int | None, override_window: int | None
) -> tuple[int, int]:
    default_limit, default_window = parse_rate_limit(
        settings.rate_limit_sensitive_value,
        fallback=(DEFAULT_LIMIT, DEFAULT_WINDOW_SECONDS),
    )
    limit = default_limit if override_limit is None else override_limit
    window = default_window if override_window is None else override_window
    return limit, window


def sensitive_route_limit(
    limit: int | None = None,
    window_sec: int | None = None,
    *,
    key_prefix: str = "sensitive",
) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        resolved_limit, resolved_window = _resolve_limits(limit, window_sec)
        if resolved_limit <= 0 or resolved_window <= 0:
            return
        ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{ip}:{request.url.path}"
        locale = resolve_locale(request=request)
        message = translate("errors.rate_limit.generic", locale=locale)
        redis_url = _resolve_redis_url()
        if redis_url:
            try:
                await enforce_rate_limit(
                    identifier=key,
                    namespace="",
                    limit=resolved_limit,
                    window_seconds=resolved_window,
                    redis_url=redis_url,
                )
            except RateLimitExceeded as exc:
                retry_after = max(0, exc.info.retry_after)
                headers = {"Retry-After": str(retry_after)} if retry_after else None
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=message,
                    headers=headers,
                ) from exc
        else:
            limiter.check(key, resolved_limit, resolved_window, message=message)

    return dependency
