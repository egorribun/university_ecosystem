"""Cache invalidations must work beyond Redis, including independent L1 caches."""

import asyncio
import re
from types import SimpleNamespace

import pytest

from app.core.cache_versioning import CacheVersionManager
from app.deps.cache import MemoryCache, NatsKVCache, TieredCache


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "tiered", "nats"])
async def test_every_supported_backend_rotates_generation(kind):
    if kind == "memory":
        cache = MemoryCache()
    elif kind == "tiered":
        cache = TieredCache(MemoryCache(), MemoryCache())
    else:

        class KV:
            def __init__(self):
                self.values = {}

            async def get(self, key):
                assert re.fullmatch(r"[a-zA-Z0-9/_=.\-]+", key)
                value = self.values.get(key)
                return SimpleNamespace(value=value) if value is not None else None

            async def put(self, key, value):
                assert re.fullmatch(r"[a-zA-Z0-9/_=.\-]+", key)
                self.values[key] = value

        cache = NatsKVCache("test", 60)
        cache._kv = KV()
    manager = CacheVersionManager("event-membership")
    before = await manager.get_version(cache)
    await manager.increment(cache)
    after = await manager.get_version(cache)
    assert before != after
    assert await manager.get_version(cache) == after
    await manager.reset(cache)
    assert await manager.get_version(cache) != after


@pytest.mark.asyncio
async def test_tiered_generation_bypasses_other_workers_stale_l1():
    shared = MemoryCache()
    first = TieredCache(MemoryCache(), shared)
    second = TieredCache(MemoryCache(), shared)
    manager = CacheVersionManager("event-membership")
    await manager.increment(first)
    old = await manager.get_version(second)
    await manager.increment(first)
    assert await manager.get_version(second) != old
    assert await manager.get_version(first) == await manager.get_version(second)


@pytest.mark.asyncio
async def test_initial_reader_cannot_overwrite_concurrent_invalidation():
    read_started = asyncio.Event()
    release_read = asyncio.Event()

    class DelayedMemory(MemoryCache):
        first = True

        async def get(self, key):
            value = await super().get(key)
            if self.first:
                self.first = False
                read_started.set()
                await release_read.wait()
            return value

    cache = DelayedMemory()
    manager = CacheVersionManager("event-membership")
    initial = asyncio.create_task(manager.get_version(cache))
    await asyncio.wait_for(read_started.wait(), timeout=1)
    await manager.increment(cache)
    current = await manager.get_version(cache)
    release_read.set()
    assert await initial != current
    assert await manager.get_version(cache) == current


@pytest.mark.asyncio
async def test_tiered_without_shared_cache_uses_process_local_generation():
    from app.deps.cache import NullCache

    cache = TieredCache(MemoryCache(), NullCache())
    manager = CacheVersionManager("event-membership")
    await manager.increment(cache)
    first = await manager.get_version(cache)
    await manager.increment(cache)
    assert await manager.get_version(cache) != first


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt", [None, 0, ""])
async def test_missing_or_corrupt_generation_never_resurrects_old_cache_key(corrupt):
    cache = MemoryCache()
    manager = CacheVersionManager("event-membership")
    await cache.set(manager.generation_key, corrupt)
    assert await manager.get_version(cache) != await manager.get_version(cache)
