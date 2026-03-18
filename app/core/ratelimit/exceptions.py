from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.ratelimit.models import RateLimitInfo


class RateLimitError(Exception):
    """Base exception for rate-limiting issues."""


class RateLimitExceeded(RateLimitError):
    """Exception raised when a rate limit is exceeded."""

    def __init__(self, info: RateLimitInfo) -> None:
        super().__init__("Rate limit exceeded")
        self.info = info


class RateLimitStorageUnavailable(RateLimitError):
    """Raised when the rate limit storage backend (Redis) is unreachable.

    Callers surface this as HTTP 503. Do NOT fall back to in-memory — that
    defeats distributed limiting in multi-process (Gunicorn) deployments.
    """
