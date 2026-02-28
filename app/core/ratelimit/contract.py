from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.ratelimit.models import RateLimitInfo


@runtime_checkable
class RateLimitStrategy(Protocol):
    """
    Domain protocol for rate limiting strategies. (DDD Strategy Pattern)
    Decouples the rate-limiting algorithm and its infrastructure (Redis/Memory)
    from the middleware and business logic.
    """

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitInfo:
        """Check if the request is allowed according to the algorithm."""
        ...
