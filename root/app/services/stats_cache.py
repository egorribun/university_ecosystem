from __future__ import annotations

import copy
from typing import Iterable, Sequence

from app.deps.cache import BaseCache, get_cache

_STATS_CACHE_PREFIX = "stats"
_STATS_KNOWN_KINDS = ("attendance", "grades", "participation")
_DEFAULT_PERIOD_KEYS = ("30d", "90d", "180d")

STATS_CACHE_TTL_SECONDS = 180


def _ensure_cache(cache: BaseCache | None) -> BaseCache:
    return cache or get_cache()


def resolve_period_key(period_key: str | None, period_days: int | None) -> str:
    key = (period_key or "").strip().lower()
    if key:
        return key
    if period_days:
        return f"{int(period_days)}d"
    return "default"


def _make_cache_key(kind: str, user_id: int, period_key: str) -> str:
    normalized_kind = kind.strip().lower()
    normalized_period = period_key.strip().lower() or "default"
    return f"{_STATS_CACHE_PREFIX}:{normalized_kind}:{int(user_id)}:{normalized_period}"


async def get_cached_stats(
    *,
    cache: BaseCache | None,
    kind: str,
    user_id: int,
    period_key: str,
    skip_cache: bool = False,
):
    backend = _ensure_cache(cache)
    if skip_cache or not backend.enabled:
        return None
    entry = await backend.get(_make_cache_key(kind, user_id, period_key))
    if entry is None or not isinstance(entry.payload, dict):
        return None
    return copy.deepcopy(entry.payload)


async def set_cached_stats(
    *,
    cache: BaseCache | None,
    kind: str,
    user_id: int,
    period_key: str,
    payload: dict[str, object],
    skip_cache: bool = False,
    ttl: int | None = None,
) -> None:
    backend = _ensure_cache(cache)
    if skip_cache or not backend.enabled:
        return
    await backend.set(
        _make_cache_key(kind, user_id, period_key),
        copy.deepcopy(payload),
        ttl=ttl or STATS_CACHE_TTL_SECONDS,
    )


async def invalidate_user_stats_cache(
    *,
    user_ids: Sequence[int] | int,
    cache: BaseCache | None = None,
    kinds: Iterable[str] | None = None,
    period_keys: Iterable[str] | None = None,
) -> None:
    backend = _ensure_cache(cache)
    if not backend.enabled:
        return
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    unique_users = {int(uid) for uid in user_ids if uid is not None}
    if not unique_users:
        return
    selected_kinds = tuple({kind.strip().lower() for kind in (kinds or _STATS_KNOWN_KINDS) if kind})
    if not selected_kinds:
        return
    chosen_periods = tuple({(period or "").strip().lower() or "default" for period in (period_keys or _DEFAULT_PERIOD_KEYS)})
    keys: list[str] = []
    for user_id in unique_users:
        for kind in selected_kinds:
            for period in chosen_periods:
                keys.append(_make_cache_key(kind, user_id, period))
    if keys:
        await backend.invalidate(*keys)
