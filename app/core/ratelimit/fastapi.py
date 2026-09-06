from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, status

from app.api.validation import raise_http_error
from app.core.config import settings
from app.core.localization import resolve_locale
from app.core.logging import get_logger
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.delay import ProgressiveDelayTracker
from app.core.ratelimit.exceptions import RateLimitExceeded, RateLimitStorageUnavailable
from app.core.ratelimit.logic import enforce_rate_limit
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import (
    extract_user_id_for_ratelimit,
    parse_rate_limit,
    resolve_client_ip,
)

logger = get_logger("app.security.ratelimit")


def sensitive_route_limit(
    limit: int | None = None,
    window_sec: int | None = None,
    *,
    key_prefix: str = "sensitive",
    limit_value: str | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency for sensitive route rate limiting."""

    async def dependency(request: Request) -> None:
        default_limit, default_window = parse_rate_limit(
            limit_value or settings.rate_limit_sensitive_value,
            fallback=(5, 60),
        )
        resolved_limit = limit if limit is not None else default_limit
        resolved_window = window_sec if window_sec is not None else default_window

        if not settings.rate_limit_enabled:
            return

        if resolved_limit <= 0 or resolved_window <= 0:
            return

        ip = resolve_client_ip(request)
        # D-08 (audit 2026-03-08): Prefer per-user keying over per-IP.
        # Authenticated users behind NAT/proxy share an IP — keying by user_id
        # removes false-positive blocks for innocent co-tenants and tightly
        # targets the actual authenticated identity.
        # Lightweight JWT decode (no DB) — used for bucketing only, not authz.
        user_id = extract_user_id_for_ratelimit(request)
        if user_id:
            key = f"{key_prefix}:user:{user_id}:{request.url.path}"
        else:
            key = f"{key_prefix}:ip:{ip}:{request.url.path}"
        locale = resolve_locale(request=request)

        try:
            strategy: RateLimitStrategy
            if settings.rate_limit_storage_backend == "redis":
                strategy = RedisSlidingWindowStrategy(settings.rate_limit_storage_uri)
            else:
                strategy = MemorySlidingWindowStrategy("sensitive")

            await enforce_rate_limit(
                identifier=key,
                limit=resolved_limit,
                window_seconds=resolved_window,
                strategy=strategy,
            )
        except RateLimitExceeded as exc:
            logger.warning(
                "Sensitive route rate limit exceeded: %s=%s, path=%s, limit=%d",
                "user" if user_id else "ip",
                user_id or ip,
                request.url.path,
                resolved_limit,
            )
            retry_after = max(0, exc.info.retry_after)
            headers = {"Retry-After": str(retry_after)} if retry_after else None
            raise_http_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "errors.rate_limit.generic",
                locale,
                headers=headers,
            )
        except RateLimitStorageUnavailable:
            # RZ-14-01: Propagate storage failure as 503 — do not silently allow.
            raise

    return dependency


def get_progressive_delay_tracker() -> ProgressiveDelayTracker:
    """FastAPI-injectable factory for ProgressiveDelayTracker."""
    try:
        redis_url = (
            settings.rate_limit_storage_uri
            if settings.rate_limit_storage_backend == "redis"
            else None
        )
    except (
        AttributeError,
        TypeError,
    ):  # RZ-25-01 + RZ-22-01: narrowed — settings access errors
        redis_url = None
    return ProgressiveDelayTracker(redis_url=redis_url)
