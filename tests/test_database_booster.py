import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.database as db_module
from app.core.database import (
    _after_cursor_execute,
    _LazyProxy,
    _on_checkout_failed,
    _on_invalidate,
    _pool_metrics,
    _query_start_time,
    _setup_slow_query_logging,
    check_replication_lag,
    configure_database,
    create_session_factory,
    get_read_db,
    init_database,
)


def test_configure_database():
    # Trigger configure_database to cover line 39
    with patch("sqlite3.register_adapter") as mock_register:
        configure_database()
        mock_register.assert_called_with(datetime.datetime, db_module.adapt_datetime)


def test_pool_health_metrics_properties():
    # Record failed checkout
    _pool_metrics.record_failed_checkout()
    assert _pool_metrics.failed_checkouts >= 1

    # Record checkouts/checkins/invalidations
    _pool_metrics.record_checkout()
    _pool_metrics.record_checkin()
    _pool_metrics.record_invalidation()

    # Call properties to get coverage
    assert _pool_metrics.total_checkouts >= 1
    assert _pool_metrics.total_checkins >= 1
    assert _pool_metrics.total_invalidations >= 1

    # Reset peak
    _pool_metrics.reset_peak_active_connections()


def test_pool_health_monitoring_callbacks():
    # Call callbacks directly to ensure coverage
    _on_invalidate(None, None, ValueError("Test DB error"))
    _on_checkout_failed(ValueError("Test DB checkout error"), MagicMock())


def test_setup_slow_query_logging_idempotence():
    # Trigger slow query logging double registration guard (line 320)
    mock_engine = MagicMock()
    mock_settings = MagicMock()
    mock_settings.slow_query_logging_enabled = True
    mock_settings.slow_query_threshold_ms = 500.0

    with patch("sqlalchemy.event.contains", return_value=True):
        _setup_slow_query_logging(mock_engine, mock_settings)
        # Should return early and not call event.listen


def test_after_cursor_execute_fallback():
    # Trigger _after_cursor_execute directly (lines 267-274)
    # 1. No start time
    _query_start_time.set(None)
    _after_cursor_execute(None, None, "SELECT 1", None, None, False)

    # 2. With start time and exceeding threshold
    _query_start_time.set(1.0)
    with (
        patch("time.perf_counter", return_value=10.0),
        patch("app.core.database._log_slow_query") as mock_log,
        patch("app.core.database.settings") as mock_settings,
    ):
        mock_settings.slow_query_threshold_ms = 100.0  # 0.1ms
        _after_cursor_execute(None, None, "SELECT 1", None, None, False)
        mock_log.assert_called()


def test_lazy_proxy_dunder_methods():
    # Create a lazy proxy with a mock target that supports context manager, iteration, etc.
    class MockTarget:
        def __init__(self):
            self.entered = False
            self.exited = False
            self.__wrapped__ = "wrapped"

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.exited = True

        def __iter__(self):
            return iter([1, 2, 3])

        def __len__(self):
            return 42

        def __contains__(self, item):
            return item == "needle"

    target = MockTarget()
    proxy = _LazyProxy(lambda: target, "test_proxy")

    # Test __setattr__ with allowed dunder
    proxy.__wrapped__ = "wrapped_val"
    assert target.__wrapped__ == "wrapped_val"

    # Test __setattr__ with disallowed attribute
    with pytest.raises(AttributeError, match="Direct attribute mutation on"):
        proxy.some_attribute = "disallowed"

    # Test async context manager (__aenter__ / __aexit__)
    async def run_context():
        async with proxy as p:
            assert p is target

    asyncio.run(run_context())
    assert target.entered
    assert target.exited

    # Test __iter__
    assert list(proxy) == [1, 2, 3]

    # Test __len__
    assert len(proxy) == 42

    # Test __contains__
    assert "needle" in proxy
    assert "haystack" not in proxy


def test_init_database_double_check_lock():
    # If database is already initialized, call init_database() again with current_settings=None
    # This triggers double-checked locking fast paths (line 588)
    init_database()
    init_database()


@pytest.mark.asyncio
async def test_get_read_db():
    gen = get_read_db()
    async for session in gen:
        assert session is not None


@pytest.mark.asyncio
async def test_check_replication_lag_none():
    with patch("app.core.database._read_replica_engine", None):
        res = await check_replication_lag()
        assert res is None


@pytest.mark.asyncio
async def test_check_replication_lag_success():
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (100.0,)
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    with patch("app.core.database._read_replica_engine", mock_engine):
        res = await check_replication_lag()
        assert res == 100.0


@pytest.mark.asyncio
async def test_check_replication_lag_error():
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = ConnectionError("Connection failed")

    with patch("app.core.database._read_replica_engine", mock_engine):
        res = await check_replication_lag()
        assert res is None


def test_create_session_factory_replica():
    # Test session factory creation with database_read_replica_url config
    mock_settings = MagicMock()
    mock_settings.database_url = "sqlite+aiosqlite:///:memory:"
    mock_settings.database_read_replica_url = "sqlite+aiosqlite:///:memory:"
    mock_settings.slow_query_logging_enabled = False

    # Mock settings to return dict/frozenset/etc values needed by _build_engine_kwargs
    mock_settings.database_pool_size = 5
    mock_settings.database_max_overflow = 10
    mock_settings.database_pool_timeout = 30
    mock_settings.database_pool_recycle = 1800
    mock_settings.database_pool_pre_ping = True

    # Just run it to make sure replica path is executed
    _eng, _sess, rep = create_session_factory(mock_settings)
    assert rep is not None
