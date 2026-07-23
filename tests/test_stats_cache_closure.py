from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.deps.cache import CacheEntry
from app.services import stats_cache


def _cache(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=enabled,
        get=AsyncMock(),
        set=AsyncMock(),
        invalidate=AsyncMock(),
    )


def test_period_and_key_helpers():
    assert stats_cache._normalize_period_key(None) == "default"
    assert stats_cache._normalize_period_key(" 30D ") == "30d"
    assert stats_cache.resolve_period_key(" 7D ", 30) == "7d"
    assert stats_cache.resolve_period_key(None, 30) == "30d"
    assert stats_cache.resolve_period_key(None, None) == "default"
    assert stats_cache._make_cache_key(" Grades ", 7, "") == "stats:grades:7:default"


@pytest.mark.asyncio
async def test_get_cached_stats_skips_disabled_invalid_and_copies_payload():
    disabled = _cache(enabled=False)
    assert (
        await stats_cache.get_cached_stats(
            cache=disabled,
            kind="attendance",
            user_id=1,
            period_key="30d",
        )
        is None
    )
    skipped = _cache()
    assert (
        await stats_cache.get_cached_stats(
            cache=skipped,
            kind="attendance",
            user_id=1,
            period_key="30d",
            skip_cache=True,
        )
        is None
    )
    skipped.get.assert_not_awaited()

    empty = _cache()
    empty.get.return_value = None
    assert (
        await stats_cache.get_cached_stats(
            cache=empty, kind="attendance", user_id=1, period_key="30d"
        )
        is None
    )

    non_mapping = _cache()
    non_mapping.get.return_value = CacheEntry("etag", [1], 1.0)
    assert (
        await stats_cache.get_cached_stats(
            cache=non_mapping, kind="attendance", user_id=1, period_key="30d"
        )
        is None
    )

    payload = {"nested": {"value": 1}}
    hit = _cache()
    hit.get.return_value = CacheEntry("etag", payload, 1.0)
    result = await stats_cache.get_cached_stats(
        cache=hit, kind="attendance", user_id=1, period_key="30d"
    )
    assert result is not None
    assert result.payload == payload
    assert result.payload is not payload


@pytest.mark.asyncio
async def test_set_cached_stats_skips_disabled_and_uses_default_or_override_ttl(
    monkeypatch,
):
    disabled = _cache(enabled=False)
    assert (
        await stats_cache.set_cached_stats(
            cache=disabled,
            kind="grades",
            user_id=1,
            period_key="30d",
            payload={"value": 1},
        )
        is None
    )
    monkeypatch.setattr(stats_cache.settings, "stats_cache_ttl_seconds", 42)
    cache = _cache()
    cache.set.return_value = CacheEntry("etag", {}, 1.0)
    result = await stats_cache.set_cached_stats(
        cache=cache,
        kind="grades",
        user_id=1,
        period_key="30d",
        payload={"value": 1},
    )
    assert result is not None
    assert cache.set.await_args.kwargs["ttl"] == 42

    await stats_cache.set_cached_stats(
        cache=cache,
        kind="grades",
        user_id=1,
        period_key="30d",
        payload={"value": 2},
        skip_cache=True,
        ttl=9,
    )
    assert cache.set.await_count == 1


@pytest.mark.asyncio
async def test_invalidate_user_stats_cache_handles_guards_and_custom_filters():
    disabled = _cache(enabled=False)
    await stats_cache.invalidate_user_stats_cache(user_ids=1, cache=disabled)
    disabled.invalidate.assert_not_awaited()

    empty = _cache()
    await stats_cache.invalidate_user_stats_cache(user_ids=[], cache=empty)
    await stats_cache.invalidate_user_stats_cache(
        user_ids=[None], cache=empty, kinds=[]
    )
    await stats_cache.invalidate_user_stats_cache(user_ids=[1], cache=empty, kinds=[""])
    empty.invalidate.assert_not_awaited()

    cache = _cache()
    await stats_cache.invalidate_user_stats_cache(
        user_ids=[uuid.UUID(int=1), uuid.UUID(int=1), 2],
        cache=cache,
        kinds=(" Attendance ", "", "grades"),
        period_keys=(" 7D ", ""),
    )
    keys = cache.invalidate.await_args.args
    assert len(keys) == 8
    assert any(key.endswith(":default") for key in keys)
    assert any(":attendance:" in key for key in keys)


@pytest.mark.asyncio
async def test_invalidate_user_stats_cache_uses_all_defaults():
    cache = _cache()
    await stats_cache.invalidate_user_stats_cache(user_ids=3, cache=cache)
    assert cache.invalidate.await_count == 1
    assert len(cache.invalidate.await_args.args) == 12


@pytest.mark.asyncio
async def test_cache_stats_decorator_covers_misses_hits_skips_and_missing_user():
    cache = _cache()
    cache.get.return_value = None
    calls = 0

    class Service:
        def __init__(self):
            self.cache = cache

        @stats_cache.cache_stats("attendance", ttl=5)
        async def load(self, user_id=None, period_days=None, skip_cache=False):
            nonlocal calls
            calls += 1
            return {"calls": calls} if user_id != "none" else None

    service = Service()
    assert await service.load(uuid.UUID(int=1), period_days=30) == {"calls": 1}
    cache.get.return_value = CacheEntry("etag", {"cached": True}, 1.0)
    assert await service.load(uuid.UUID(int=1), period_days=30) == {"cached": True}
    assert await service.load("none", skip_cache=True) is None
    assert await service.load(None) == {"calls": 3}


@pytest.mark.asyncio
async def test_cache_stats_decorator_resolves_user_object_and_global_cache(monkeypatch):
    cache = _cache()
    cache.get.return_value = None
    monkeypatch.setattr(stats_cache, "get_cache", lambda: cache)
    calls = 0

    @stats_cache.cache_stats("grades")
    async def load(self, user_id, period_key="default"):
        nonlocal calls
        calls += 1
        return {"calls": calls}

    service = SimpleNamespace(cache=None)
    user = SimpleNamespace(id=uuid.UUID(int=5))
    assert await load(service, user, period_key="90d") == {"calls": 1}
