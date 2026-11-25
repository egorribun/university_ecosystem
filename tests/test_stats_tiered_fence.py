from __future__ import annotations

from uuid import uuid4

import fakeredis.aioredis
import pytest

from app.deps.cache import MemoryCache, RedisCache, TieredCache
from app.services import stats_cache
from app.services.stats_fill_fence import StatsFillFence


@pytest.mark.asyncio
async def test_peer_l1s_do_not_promote_marker_and_see_completed_payload():
    user_id = uuid4()
    left_l1 = MemoryCache(default_ttl=60)
    right_l1 = MemoryCache(default_ttl=60)
    l2 = RedisCache("unused", default_ttl=180)
    l2._client = fakeredis.aioredis.FakeRedis()
    left = TieredCache(left_l1, l2)
    right = TieredCache(right_l1, l2)
    fence = StatsFillFence(left)
    key = stats_cache.make_stats_cache_key("grades", user_id, "30d")
    token = "a" * 32
    assert fence.supported
    assert await fence.reserve(key, token, 30) is True
    for tier in (left, right):
        assert (
            await stats_cache.get_cached_stats(
                cache=tier, kind="grades", user_id=user_id, period_key="30d"
            )
            is None
        )
    assert await left_l1.get(key) is None
    assert await right_l1.get(key) is None
    assert await fence.complete(key, token, {"average": 5.0}, 180) is True
    for tier in (left, right):
        entry = await stats_cache.get_cached_stats(
            cache=tier, kind="grades", user_id=user_id, period_key="30d"
        )
        assert entry.payload["average"] == 5.0
    assert (await l2.get(key)).ttl_seconds == 180.0
