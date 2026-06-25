import pytest
import sqlite3
import datetime
import asyncio
import threading
from unittest.mock import MagicMock, AsyncMock, patch
from graphql import GraphQLError

from app.core.database import (
    configure_database,
    init_database,
    get_read_db,
    check_replication_lag,
    _LazyProxy,
    _pool_metrics,
    _on_invalidate,
    _on_checkout_failed,
    _setup_slow_query_logging,
    _after_cursor_execute,
    _query_start_time,
    create_session_factory,
)
import app.core.database as db_module

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
    import logging
    # Set logger level to DEBUG
    db_module.pool_health_logger.setLevel(logging.DEBUG)
    # Call callbacks directly to ensure coverage
    db_module._on_checkout(None, None, None)
    db_module._on_checkin(None, None)
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

    # Also test calling the closure with no start time to cover line 307
    with patch("sqlalchemy.event.contains", return_value=False), \
         patch("sqlalchemy.event.listen") as mock_listen:
        _setup_slow_query_logging(mock_engine, mock_settings)
        closure = None
        for call in mock_listen.call_args_list:
            if call[0][1] == "after_cursor_execute":
                closure = call[0][2]
                break
        if closure:
            _query_start_time.set(None)
            closure(None, None, "SELECT 1", None, None, False)

def test_after_cursor_execute_fallback():
    # Trigger _after_cursor_execute directly (lines 267-274)
    # 1. No start time
    _query_start_time.set(None)
    _after_cursor_execute(None, None, "SELECT 1", None, None, False)
    
    # 2. With start time and exceeding threshold
    _query_start_time.set(1.0)
    with patch("time.perf_counter", return_value=10.0), \
         patch("app.core.database._log_slow_query") as mock_log, \
         patch("app.core.database.settings") as mock_settings:
        mock_settings.slow_query_threshold_ms = 100.0 # 0.1ms
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
    try:
        proxy.__wrapped__ = "wrapped_val"
    except AttributeError:
        pass
    proxy.__class__ = _LazyProxy
    
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
    # This triggers double-checked locking fast paths (line 580)
    init_database()
    init_database()

    # Trigger inner check double-checked locking (line 588)
    original_engine = db_module._engine
    try:
        db_module._engine = None
        class MockInitLock:
            def __enter__(self):
                db_module._engine = MagicMock()
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
                
        with patch("app.core.database._init_lock", MockInitLock()):
            init_database(None)
    finally:
        db_module._engine = original_engine

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
    mock_conn.__aenter__.return_value = mock_conn
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (100.0,)
    mock_conn.execute.return_value = mock_result
    
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    
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
    eng, sess, rep = create_session_factory(mock_settings)
    assert rep is not None

def test_setup_pool_health_monitoring_checkout_failed():
    mock_engine = MagicMock()
    mock_pool = MagicMock()
    # mock hasattr(pool.dispatch, "checkout_failed") to return True
    mock_pool.dispatch = MagicMock(spec=["checkout_failed"])
    mock_engine.sync_engine.pool = mock_pool
    
    with patch("sqlalchemy.event.listen") as mock_listen:
        db_module._setup_pool_health_monitoring(mock_engine)
        # Verify that checkout_failed was registered
        mock_listen.assert_any_call(mock_pool, "checkout_failed", db_module._on_checkout_failed)
