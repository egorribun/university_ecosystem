from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.core.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

F = TypeVar("F", bound=Callable[..., object])


def _default_limits() -> list[str] | None:
    limits = settings.rate_limit_default_list
    return limits or None


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=_default_limits(),
    storage_uri=settings.rate_limit_storage_uri,
    headers_enabled=settings.rate_limit_headers_enabled,
    enabled=settings.rate_limit_enabled,
)


def limit_if_configured(limit_value: str | None) -> Callable[[F], F]:
    if not limit_value:

        def decorator(func: F) -> F:
            return func

        return decorator
    return limiter.limit(limit_value)


def sensitive_route_limit() -> Callable[[F], F]:
    return limit_if_configured(settings.rate_limit_sensitive_value)
