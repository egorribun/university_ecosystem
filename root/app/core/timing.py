"""
Request timing middleware for API latency monitoring.

Logs and records metrics for slow API requests.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

logger = logging.getLogger("app.timing")

# Threshold for slow request logging (milliseconds)
SLOW_REQUEST_THRESHOLD_MS: float = 500.0


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Middleware to track and log API request timing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate elapsed time
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Add timing header
        response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"

        # Log slow requests
        if elapsed_ms >= SLOW_REQUEST_THRESHOLD_MS:
            path = request.url.path
            method = request.method
            status = response.status_code

            logger.warning(
                "Slow request: %s %s - %.2fms (status=%d)",
                method,
                path,
                elapsed_ms,
                status,
                extra={
                    "elapsed_ms": elapsed_ms,
                    "method": method,
                    "path": path,
                    "status_code": status,
                    "slow_request": True,
                },
            )

        return response


def create_timing_middleware() -> type[RequestTimingMiddleware]:
    """Factory for request timing middleware."""
    return RequestTimingMiddleware


__all__ = ["RequestTimingMiddleware", "create_timing_middleware", "SLOW_REQUEST_THRESHOLD_MS"]
