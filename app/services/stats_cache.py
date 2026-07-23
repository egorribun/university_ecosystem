from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from app.core.config import settings
from app.deps.cache import BaseCache, CacheEntry, get_cache

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_STATS_CACHE_PREFIX = "stats"
_STATS_KNOWN_KINDS = ("attendance", "grades", "participation")
_DEFAULT_PERIOD_KEYS = ("30d", "90d", "180d")


def _normalize_period_key(period_key: str | None) -> str:
    normalized = (period_key or "").strip().lower()
    return normalized or "default"


def _ensure_cache(cache: BaseCache | None) -> BaseCache:
    return cache or get_cache()


def resolve_period_key(period_key: str | None, period_days: int | None) -> str:
    key = (period_key or "").strip().lower()
    if key:
        return key
    if period_days:
        return f"{int(period_days)}d"
    return "default"


def _make_cache_key(kind: str, user_id: uuid.UUID | int | str, period_key: str) -> str:
    normalized_kind = kind.strip().lower()
    normalized_period = _normalize_period_key(period_key)
    return f"{_STATS_CACHE_PREFIX}:{normalized_kind}:{user_id!s}:{normalized_period}"


async def get_cached_stats(
    *,
    cache: BaseCache | None,
    kind: str,
    user_id: uuid.UUID | int | str,
    period_key: str,
    skip_cache: bool = False,
) -> CacheEntry | None:
    backend = _ensure_cache(cache)
    if skip_cache or not backend.enabled:
        return None
    entry = await backend.get(_make_cache_key(kind, user_id, period_key))
    if entry is None or not isinstance(entry.payload, dict):
        return None
    return CacheEntry(
        etag=entry.etag,
        payload=copy.deepcopy(entry.payload),
        stored_at=entry.stored_at,
    )


async def set_cached_stats(
    *,
    cache: BaseCache | None,
    kind: str,
    user_id: uuid.UUID | int | str,
    period_key: str,
    payload: dict[str, object],
    skip_cache: bool = False,
    ttl: int | None = None,
) -> CacheEntry | None:
    backend = _ensure_cache(cache)
    if skip_cache or not backend.enabled:
        return None
    effective_ttl = ttl if ttl is not None else settings.stats_cache_ttl_seconds
    return await backend.set(
        _make_cache_key(kind, user_id, period_key),
        copy.deepcopy(payload),
        ttl=effective_ttl,
    )


async def invalidate_user_stats_cache(
    *,
    user_ids: Sequence[uuid.UUID | int] | uuid.UUID | int,
    cache: BaseCache | None = None,
    kinds: Iterable[str] | None = None,
    period_keys: Iterable[str] | None = None,
) -> None:
    backend = _ensure_cache(cache)
    if not backend.enabled:
        return
    if isinstance(user_ids, int | uuid.UUID):
        user_ids = [user_ids]
    unique_users = {str(uid) for uid in user_ids if uid is not None}
    if not unique_users:
        return
    selected_kinds = tuple(
        {kind.strip().lower() for kind in (kinds or _STATS_KNOWN_KINDS) if kind}
    )
    if not selected_kinds:
        return
    normalized_periods = {
        _normalize_period_key(period)
        for period in (period_keys if period_keys else _DEFAULT_PERIOD_KEYS)
    }
    normalized_periods.add("default")
    chosen_periods = tuple(normalized_periods)
    keys: list[str] = []
    for user_id in unique_users:
        for kind in selected_kinds:
            for period in chosen_periods:
                keys.append(_make_cache_key(kind, user_id, period))
    if (
        keys
    ):  # pragma: no branch - user/kind/default period invariants make this non-empty
        await backend.invalidate(*keys)


F = TypeVar("F", bound=Callable[..., Any])


def cache_stats(kind: str, ttl: int | None = None) -> Callable[[F], F]:
    """Decorator to automatically handle caching for statistics methods.

    Expects the first argument to be 'self' (a service instance with a 'cache' attribute/property)
    or just uses the global cache.
    Expects 'user_id' and 'period_key' or 'period_days' as arguments.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            import inspect

            # Resolve arguments
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            arguments = bound_args.arguments

            user_id = arguments.get("user_id")
            if user_id and hasattr(user_id, "id"):
                user_id = user_id.id

            if user_id is None:
                return await func(self, *args, **kwargs)

            period_key = arguments.get("period_key")
            period_days = arguments.get("period_days")
            skip_cache = kwargs.get("skip_cache", False)

            resolved_p_key = resolve_period_key(period_key, period_days)

            # Access cache from self or global
            cache = getattr(self, "cache", None)

            # 1. Try Cache
            if not skip_cache:
                entry = await get_cached_stats(
                    cache=cache,
                    kind=kind,
                    user_id=user_id,
                    period_key=resolved_p_key,
                )
                if entry is not None:
                    return entry.payload

            # 2. Call Method
            result = await func(self, *args, **kwargs)

            # 3. Store Cache
            if result is not None:
                await set_cached_stats(
                    cache=cache,
                    kind=kind,
                    user_id=user_id,
                    period_key=resolved_p_key,
                    payload=result,
                    ttl=ttl,
                )

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
