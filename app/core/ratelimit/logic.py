from __future__ import annotations

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.exceptions import RateLimitExceeded
from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import compose_identifier


async def check_rate_limit(
    *,
    identifier: str,
    namespace: str = "",
    limit: int,
    window_seconds: int,
    redis_url: str | None = None,
) -> RateLimitInfo:
    """Check a rate limit for an arbitrary identifier."""
    key = compose_identifier(namespace, identifier)
    if redis_url and redis_url.lower().startswith(("redis://", "rediss://")):
        try:
            strategy = RedisSlidingWindowStrategy(redis_url)
            return await strategy.check(key, limit, window_seconds)
        except (RedisError, OSError):
            pass

    strategy = MemorySlidingWindowStrategy(namespace)
    return await strategy.check(identifier, limit, window_seconds)


def get_default_strategy(namespace: str = "") -> RateLimitStrategy:
    """Get the default rate limit strategy based on application settings."""
    if settings.rate_limit_storage_backend == "redis":
        return RedisSlidingWindowStrategy(settings.rate_limit_storage_uri)
    return MemorySlidingWindowStrategy(namespace)


async def enforce_rate_limit(
    *,
    identifier: str,
    limit: int,
    window_seconds: int,
    strategy: RateLimitStrategy,
) -> RateLimitInfo:
    """Enforce a rate limit, raising RateLimitExceeded if exceeded."""
    try:
        info = await strategy.check(
            key=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RedisError:
        # Fallback to in-memory limiting
        fallback = MemorySlidingWindowStrategy("fallback")
        info = await fallback.check(
            key=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )

    if not info.allowed:
        raise RateLimitExceeded(info)
    return info
