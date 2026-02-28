from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RateLimitInfo:
    """Core rate limit state."""

    allowed: bool
    remaining: int
    retry_after: int


@dataclass(slots=True)
class ProgressiveDelayInfo:
    """Information about progressive delay state."""

    failures: int
    delay_seconds: float
    should_delay: bool


@dataclass(frozen=True, slots=True)
class EndpointRateLimit:
    """Configuration for endpoint-specific rate limits."""

    pattern: str  # Path prefix pattern
    limit: int
    window_seconds: int
