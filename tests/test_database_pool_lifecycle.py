from __future__ import annotations

from contextlib import AsyncExitStack

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core import database as database_module


@pytest.mark.asyncio
async def test_real_async_pool_metrics_track_normal_checkins(monkeypatch):
    metrics = database_module.PoolHealthMetrics()
    monkeypatch.setattr(database_module, "_pool_metrics", metrics)
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=1,
    )
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        database_module._setup_pool_health_monitoring(engine)
        first = await stack.enter_async_context(engine.connect())
        second = await stack.enter_async_context(engine.connect())
        assert metrics.active_connections == 2

        await first.close()
        assert metrics.active_connections == 1
        assert (await second.exec_driver_sql("SELECT 1")).scalar_one() == 1
        assert metrics.active_connections == 1
        await second.close()
        assert metrics.get_snapshot() == {
            "total_checkouts": 2,
            "total_checkins": 2,
            "total_invalidations": 0,
            "active_connections": 0,
            "peak_active_connections": 2,
            "failed_checkouts": 0,
        }


@pytest.mark.asyncio
async def test_real_async_pool_invalidation_checkin_and_record_reuse(monkeypatch):
    metrics = database_module.PoolHealthMetrics()
    monkeypatch.setattr(database_module, "_pool_metrics", metrics)
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=1,
    )
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        database_module._setup_pool_health_monitoring(engine)
        checkout_records = []
        event.listen(
            engine.sync_engine.pool,
            "checkout",
            lambda _dbapi, record, _proxy: checkout_records.append(record),
        )
        first = await stack.enter_async_context(engine.connect())
        second = await stack.enter_async_context(engine.connect())
        first_record = checkout_records[0]
        assert metrics.active_connections == 2

        # Hard invalidation returns its pool record before this await completes.
        await first.invalidate()
        assert metrics.total_invalidations == 1
        assert metrics.total_checkins == 1
        assert metrics.active_connections == 1
        await first.close()
        assert metrics.total_checkins == 1
        assert metrics.active_connections == 1
        assert (await second.exec_driver_sql("SELECT 1")).scalar_one() == 1

        replacement = await stack.enter_async_context(engine.connect())
        assert checkout_records[-1] is first_record
        assert metrics.active_connections == 2
        assert (await replacement.exec_driver_sql("SELECT 1")).scalar_one() == 1
        await replacement.close()
        assert metrics.active_connections == 1
        await second.close()
        assert metrics.get_snapshot() == {
            "total_checkouts": 3,
            "total_checkins": 3,
            "total_invalidations": 1,
            "active_connections": 0,
            "peak_active_connections": 2,
            "failed_checkouts": 0,
        }


@pytest.mark.asyncio
async def test_real_async_pool_idle_invalidation_preserves_other_checkout(monkeypatch):
    metrics = database_module.PoolHealthMetrics()
    monkeypatch.setattr(database_module, "_pool_metrics", metrics)
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=1,
    )
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        database_module._setup_pool_health_monitoring(engine)
        checkout_records = []
        event.listen(
            engine.sync_engine.pool,
            "checkout",
            lambda _dbapi, record, _proxy: checkout_records.append(record),
        )
        first = await stack.enter_async_context(engine.connect())
        second = await stack.enter_async_context(engine.connect())
        idle_record = checkout_records[0]
        await first.close()
        assert metrics.total_checkins == 1
        assert metrics.active_connections == 1

        # Run the synchronous pool API in SQLAlchemy's async-driver bridge.
        await second.run_sync(lambda _connection: idle_record.invalidate())
        assert metrics.total_invalidations == 1
        assert metrics.total_checkins == 1
        assert metrics.active_connections == 1
        assert (await second.exec_driver_sql("SELECT 1")).scalar_one() == 1
        await second.close()
        assert metrics.get_snapshot() == {
            "total_checkouts": 2,
            "total_checkins": 2,
            "total_invalidations": 1,
            "active_connections": 0,
            "peak_active_connections": 2,
            "failed_checkouts": 0,
        }
