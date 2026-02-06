import asyncio

import pytest

from app.core.database import PoolHealthMetrics


@pytest.mark.asyncio
async def test_pool_metrics_concurrency():
    """
    Verify that removing the lock didn't break consistency
    for concurrent ASYNC tasks (which run in a single thread).
    """
    metrics = PoolHealthMetrics()

    # Simulate N concurrent connections checkout/checkin
    N = 1000

    async def worker():
        metrics.record_checkout()
        # Simulate some work - gives event loop chance to switch if we were awaiting
        await asyncio.sleep(0.0001)
        metrics.record_checkin()

    tasks = [worker() for _ in range(N)]
    await asyncio.gather(*tasks)

    snapshot = metrics.get_snapshot()

    assert snapshot["total_checkouts"] == N
    assert snapshot["total_checkins"] == N
    assert snapshot["active_connections"] == 0
    assert snapshot["peak_active_connections"] > 0
    # Peak depends on scheduling, but should be > 0.


@pytest.mark.asyncio
async def test_pool_metrics_logic():
    metrics = PoolHealthMetrics()

    metrics.record_checkout()
    metrics.record_checkout()
    assert metrics.active_connections == 2
    assert metrics.peak_active_connections == 2

    metrics.record_checkin()
    assert metrics.active_connections == 1

    metrics.record_invalidation()
    assert metrics.active_connections == 0
    assert metrics.total_invalidations == 1
