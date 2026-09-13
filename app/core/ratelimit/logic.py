from __future__ import annotations

import functools

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.ratelimit.circuit_breaker import get_circuit_breaker
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.exceptions import RateLimitExceeded
from app.core.ratelimit.models import RateLimitInfo
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import compose_identifier

_log = get_logger(__name__)


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
    """Check a rate limit for an arbitrary identifier.

    The function picks one of three execution paths depending on inputs:

    * ``settings.rate_limit_enabled is False`` — short-circuits with
      ``RateLimitInfo(allowed=True, remaining=limit, retry_after=0)`` so
      tests / dev environments are unaffected.
    * ``redis_url`` looks like a Redis URL AND the circuit breaker is
      not OPEN — runs ``RedisSlidingWindowStrategy`` with a Lua script.
      On ``RedisError`` / ``OSError`` the breaker records a failure and the
      request falls through to the in-memory fallback below.
    * Fallback or no-redis path — uses ``MemorySlidingWindowStrategy`` at
      ``max(limit // 2, 1)``. The 50 % cap prevents a stale memory window
      from acting as a permissive backdoor when Redis is down across
      multiple workers.

    Raises ``ValueError`` on ``limit <= 0`` or ``window_seconds <= 0`` —
    both are silent-misconfiguration vectors and must surface immediately.

    Args:
        identifier: Per-key value (user id, IP, anonymous nonce, etc.).
        namespace: Logical bucket prefix; combined with ``identifier`` via
            ``compose_identifier``.
        limit: Maximum allowed requests inside ``window_seconds``. Must be
            positive.
        window_seconds: Sliding-window length in seconds. Must be positive.
        redis_url: Optional Redis connection URL. When None / non-Redis,
            the in-memory strategy is used directly (without the breaker
            or the 50 % fallback cap).

    Returns:
        ``RateLimitInfo`` describing whether the call is allowed, how many
        requests remain inside the current window, and the seconds until
        the oldest request slides out.
    """
    # RZ-W19-05 (audit 2026-03-24 Wave 19): validate invariants to prevent
    # silent misconfiguration (e.g., limit=0 disables protection entirely,
    # negative window causes Lua script errors in Redis).
    if limit <= 0:
        raise ValueError(f"rate limit must be positive, got {limit}")
    if window_seconds <= 0:
        raise ValueError(f"rate limit window must be positive, got {window_seconds}")

    # RZ-HARDEN: Respect global toggle. Test environments now explicitly enable it if needed.
    if not settings.rate_limit_enabled:
        return RateLimitInfo(allowed=True, remaining=limit, retry_after=0)

    key = compose_identifier(namespace, identifier)
    if redis_url and redis_url.lower().startswith(("redis://", "rediss://")):
        cb = get_circuit_breaker()
        strategy = _get_redis_strategy(redis_url)

        if cb.allow_request():
            try:
                result = await strategy.check(key, limit, window_seconds)
                cb.record_success()
                return result
            except (RedisError, OSError) as exc:
                cb.record_failure()
                _log.warning(
                    "rate_limit_storage_unavailable_fallback",
                    extra={"identifier": identifier, "error": str(exc)},
                )
        else:
            _log.debug(
                "rate_limit_circuit_open_fallback",
                extra={"identifier": identifier, "state": cb.state.name},
            )

        # PERF-30-01: Circuit open or Redis failure — fail-closed with 50% local limit.
        fallback_limit = max(limit // 2, 1)
        fallback_strategy = MemorySlidingWindowStrategy("fallback")
        return await fallback_strategy.check(key, fallback_limit, window_seconds)

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
    # RZ-HARDEN: Respect global toggle.
    if not settings.rate_limit_enabled:
        return RateLimitInfo(allowed=True, remaining=limit, retry_after=0)

    cb = get_circuit_breaker()

    if cb.allow_request():
        try:
            info = await strategy.check(
                key=identifier,
                limit=limit,
                window_seconds=window_seconds,
            )
            cb.record_success()
        except (RedisError, OSError) as exc:
            cb.record_failure()
            _log.warning(
                "rate_limit_storage_unavailable_fallback",
                extra={"identifier": identifier, "error": str(exc)},
            )
            # PERF-30-01: Circuit breaker recorded failure — use 50% fallback.
            fallback_limit = max(limit // 2, 1)
            fallback_strategy = MemorySlidingWindowStrategy("fallback")
            info = await fallback_strategy.check(
                key=identifier, limit=fallback_limit, window_seconds=window_seconds
            )
    else:
        # PERF-30-01: Circuit open — skip Redis entirely, use fallback.
        fallback_limit = max(limit // 2, 1)
        fallback_strategy = MemorySlidingWindowStrategy("fallback")
        info = await fallback_strategy.check(
            key=identifier, limit=fallback_limit, window_seconds=window_seconds
        )

    if not info.allowed:
        raise RateLimitExceeded(info)
    return info
