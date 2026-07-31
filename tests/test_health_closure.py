"""Closure tests for optional pool statistics and health success/timeout paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.health import (
    HealthStatus,
    check_database_connectivity,
    check_database_health,
    check_spicedb_health,
)


@pytest.mark.asyncio
async def test_database_health_handles_engine_without_pool():
    db = SimpleNamespace(execute=AsyncMock())

    with patch(
        "app.core.database.get_read_engine",
        return_value=SimpleNamespace(pool=None),
    ):
        result = await check_database_health(db)

    assert result.status is HealthStatus.HEALTHY
    assert result.pool_size is None
    assert result.pool_checked_out is None


@pytest.mark.asyncio
async def test_database_connectivity_returns_false_on_wait_timeout():
    db = SimpleNamespace(execute=AsyncMock())

    async def timeout_and_close(coro, *, timeout):
        coro.close()
        raise TimeoutError

    with patch(
        "app.core.health.asyncio.wait_for",
        new_callable=AsyncMock,
        side_effect=timeout_and_close,
    ):
        assert await check_database_connectivity(db, timeout_ms=25) is False


@pytest.mark.asyncio
async def test_spicedb_health_returns_ok_when_channel_is_ready():
    channel = SimpleNamespace(channel_ready=AsyncMock())

    async def channel_source():
        yield channel

    with patch("app.core.spicedb.get_async_spicedb_channel", channel_source):
        status, latency = await check_spicedb_health()

    assert status == "ok"
    assert latency >= 0


@pytest.mark.asyncio
async def test_spicedb_health_reports_disabled_when_channel_is_none():
    async def channel_source():
        yield None

    with patch("app.core.spicedb.get_async_spicedb_channel", channel_source):
        assert await check_spicedb_health() == ("disabled", 0.0)


@pytest.mark.asyncio
async def test_spicedb_health_reports_error_on_channel_timeout():
    channel = SimpleNamespace(channel_ready=AsyncMock(side_effect=TimeoutError))

    async def channel_source():
        yield channel

    with patch("app.core.spicedb.get_async_spicedb_channel", channel_source):
        status, latency = await check_spicedb_health()

    assert status == "error"
    assert latency >= 0


@pytest.mark.asyncio
async def test_spicedb_health_reports_error_when_channel_source_fails():
    async def channel_source():
        raise RuntimeError("spicedb unavailable")
        yield None

    with patch("app.core.spicedb.get_async_spicedb_channel", channel_source):
        status, latency = await check_spicedb_health()

    assert status == "error"
    assert latency >= 0
