"""
Request timing middleware for API latency monitoring.

Logs and records metrics for slow API requests.
"""

# MED-W19: converted from BaseHTTPMiddleware to a raw ASGI middleware class to
# avoid BaseHTTPMiddleware's full-body buffering which prevents streaming.
# X-Response-Time header is now opt-in via settings.expose_timing_header to
# avoid leaking internal timing data to external clients in production.

import asyncio
import time
from typing import Any, TypeVar

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.timing")

# Threshold for slow request logging (milliseconds)
SLOW_REQUEST_THRESHOLD_MS: float = 500.0

T = TypeVar("T")


async def ensure_minimum_time(start_time: float, min_duration_seconds: float) -> None:
    """
    Ensures that the execution takes at least min_duration_seconds.
    Used to mitigate timing attacks.
    """
    elapsed = time.perf_counter() - start_time
    shortfall = min_duration_seconds - elapsed
    if shortfall > 0:
        await asyncio.sleep(shortfall)


class RequestTimingMiddleware:
    """Raw ASGI middleware to track and log API request timing."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code: int = 200

        async def _send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                status_code = message.get("status", 200)

                if settings.expose_timing_header:
                    # MED-W19: only inject header when explicitly opted in
                    raw_headers: list[tuple[bytes, bytes]] = list(
                        message.get("headers", [])
                    )
                    raw_headers.append(
                        (
                            b"x-response-time",
                            f"{elapsed_ms:.2f}ms".encode("latin-1"),
                        )
                    )
                    message = {**message, "headers": raw_headers}

            await send(message)

        await self.app(scope, receive, _send_wrapper)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if elapsed_ms >= SLOW_REQUEST_THRESHOLD_MS:
            path: str = scope.get("path", "")
            method: str = scope.get("method", "")
            logger.warning(
                "Slow request: %s %s - %.2fms (status=%d)",
                method,
                path,
                elapsed_ms,
                status_code,
                extra={
                    "elapsed_ms": elapsed_ms,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "slow_request": True,
                },
            )


def create_timing_middleware() -> type[RequestTimingMiddleware]:
    """Factory for request timing middleware."""
    return RequestTimingMiddleware


__all__ = [
    "SLOW_REQUEST_THRESHOLD_MS",
    "RequestTimingMiddleware",
    "create_timing_middleware",
]
