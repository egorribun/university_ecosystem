from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request, status


class MemoryLimiter:
    def __init__(self) -> None:
        self.bucket: dict[str, list[float]] = {}

    def check(self, key: str, limit: int, window_sec: int) -> None:
        now = time.time()
        arr = [t for t in self.bucket.get(key, []) if now - t < window_sec]
        if len(arr) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов",
            )
        arr.append(now)
        self.bucket[key] = arr


limiter = MemoryLimiter()


def sensitive_route_limit(limit: int = 5, window_sec: int = 60) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            ip = request.client.host if request.client else "unknown"
            key = f"sensitive:{ip}:{request.url.path}"
            limiter.check(key, limit, window_sec)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator