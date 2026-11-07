"""Hermetic tests for CacheVersionManager (app/core/cache_versioning.py).

Covers the cache-disabled / non-Redis / cache-resolved-from-global branches of
get_version / increment / reset plus the pure-logic key builders. The Redis
fast-paths (RedisCache + a live client) are exercised by the events/news API
coverage tests; the RedisError except arms (78-79, 93-94) need a real failing
Redis client and stay out of this hermetic slice (fakeredis has no Lua, §3.16).
"""

from __future__ import annotations

import pytest

from app.core.cache_versioning import (
    CacheVersionManager,
    events_cache_version,
    news_cache_version,
)
from app.deps.cache import MemoryCache, NullCache, set_cache_backend


@pytest.fixture(autouse=True)
def _reset_cache_backend():
    yield
    set_cache_backend(None)


@pytest.mark.asyncio
async def test_get_version_zero_when_cache_disabled() -> None:
    mgr = CacheVersionManager(prefix="x:list")
    assert await mgr.get_version(NullCache()) == "0"


@pytest.mark.asyncio
async def test_get_version_for_enabled_non_redis_cache_uses_unique_generations() -> (
    None
):
    mgr = CacheVersionManager(prefix="x:list")
    cache = MemoryCache()
    initial = await mgr.get_version(cache)
    await mgr.increment(cache)
    assert await mgr.get_version(cache) != initial


@pytest.mark.asyncio
async def test_get_version_resolves_cache_from_global_when_none() -> None:
    set_cache_backend(NullCache())
    mgr = CacheVersionManager(prefix="x:list")
    assert await mgr.get_version() == "0"


@pytest.mark.asyncio
async def test_increment_disabled_and_global_are_noops_non_redis_rotates() -> None:
    mgr = CacheVersionManager(prefix="x:list")
    disabled = NullCache()
    assert await mgr.get_version(disabled) == "0"
    assert (await mgr.increment(disabled)) is None
    assert await mgr.get_version(disabled) == "0"

    memory = MemoryCache()
    before = await mgr.get_version(memory)
    assert (await mgr.increment(memory)) is None
    assert await mgr.get_version(memory) != before

    set_cache_backend(NullCache())
    assert (await mgr.increment()) is None
    assert await mgr.get_version() == "0"


@pytest.mark.asyncio
async def test_reset_disabled_and_global_are_noops_non_redis_rotates() -> None:
    mgr = CacheVersionManager(prefix="x:list")
    disabled = NullCache()
    assert (await mgr.reset(disabled)) is None
    assert await mgr.get_version(disabled) == "0"

    memory = MemoryCache()
    before = await mgr.get_version(memory)
    assert (await mgr.reset(memory)) is None
    assert await mgr.get_version(memory) != before

    set_cache_backend(NullCache())
    assert (await mgr.reset()) is None
    assert await mgr.get_version() == "0"


def test_version_key_property() -> None:
    assert CacheVersionManager(prefix="news:list").version_key == "news:list:version"


def test_build_cache_key_is_order_independent_and_prefixed() -> None:
    mgr = CacheVersionManager(prefix="news:list")
    a = mgr.build_cache_key(locale="en", version="3", limit=10, cursor="abc")
    b = mgr.build_cache_key(locale="en", version="3", cursor="abc", limit=10)
    assert a == b  # sort_keys → param order irrelevant
    assert a.startswith("news:list:3:en:")
    # Distinct params → distinct key.
    assert mgr.build_cache_key(locale="en", version="3", limit=20) != a


def test_module_global_managers_have_expected_prefixes() -> None:
    assert events_cache_version.prefix == "events:list"
    assert news_cache_version.prefix == "news:list"
