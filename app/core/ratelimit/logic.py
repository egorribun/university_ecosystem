from __future__ import annotations

import functools
import logging
import os

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.exceptions import RateLimitExceeded, RateLimitStorageUnavailable
from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import compose_identifier

_log = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def _get_redis_strategy(redis_url: str) -> RedisSlidingWindowStrategy:
    """Return a cached strategy instance per redis_url (TD-14-01)."""
    return RedisSlidingWindowStrategy(redis_url)


async def check_rate_limit(
    *,
    identifier: str,
    namespace: str = "",
    limit: int,
    window_seconds: int,
    redis_url: str | None = None,
) -> RateLimitInfo:
    """Check a rate limit for an arbitrary identifier."""
    # RZ-HARDEN: Respect global toggle and test environments
    if not settings.rate_limit_enabled or os.environ.get("ENVIRONMENT") == "testing":
        return RateLimitInfo(allowed=True, remaining=limit, retry_after=0)

    key = compose_identifier(namespace, identifier)
    if redis_url and redis_url.lower().startswith(("redis://", "rediss://")):
        strategy = _get_redis_strategy(redis_url)
        try:
            return await strategy.check(key, limit, window_seconds)
        except (RedisError, OSError) as exc:
            _log.error(
                "rate_limit_storage_unavailable",
                extra={"identifier": identifier, "error": str(exc)},
            )
            raise RateLimitStorageUnavailable("Rate limit backend unreachable") from exc

    # Non-distributed mode: in-memory is only acceptable when Redis is not configured.
    _log.warning("rate_limit_memory_mode", extra={"reason": "no redis_url configured"})
    memory_strategy = MemorySlidingWindowStrategy(namespace)
    return await memory_strategy.check(identifier, limit, window_seconds)


def get_default_strategy(namespace: str = "") -> RateLimitStrategy:
    """Get the default rate limit strategy based on application settings."""
    if settings.rate_limit_storage_backend == "redis":
        return _get_redis_strategy(settings.rate_limit_storage_uri)
    return MemorySlidingWindowStrategy(namespace)


async def enforce_rate_limit(
    *,
    identifier: str,
    limit: int,
    window_seconds: int,
    strategy: RateLimitStrategy,
) -> RateLimitInfo:
    """Enforce a rate limit, raising RateLimitExceeded if exceeded."""
    # RZ-HARDEN: Respect global toggle and test environments
    if not settings.rate_limit_enabled or os.environ.get("ENVIRONMENT") == "testing":
        return RateLimitInfo(allowed=True, remaining=limit, retry_after=0)

    try:
        info = await strategy.check(
            key=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RedisError as exc:
        _log.error(
            "rate_limit_storage_unavailable",
            extra={"identifier": identifier, "error": str(exc)},
        )
        raise RateLimitStorageUnavailable("Rate limit backend unreachable") from exc

    if not info.allowed:
        raise RateLimitExceeded(info)
    return info
