from __future__ import annotations

import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core import database as database_module


def test_adapt_datetime_and_sqlite_connection_configuration():
    value = datetime(2026, 7, 27, 12, 34, 56)
    assert database_module.adapt_datetime(value) == "2026-07-27T12:34:56"

    connection = sqlite3.connect(":memory:")
    try:
        database_module.set_sqlite_pragma(connection, None)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("SELECT pg_sleep(0)").fetchone() == (None,)
    finally:
        connection.close()


def test_sqlite_connection_wrapper_handles_registration_failure():
    class _RawConnection:
        def create_function(self, *args):
            raise RuntimeError("registration unavailable")

    class _ConnectionWrapper:
        def __init__(self):
            self.dbapi_connection = SimpleNamespace(_conn=_RawConnection())

    database_module.set_sqlite_pragma(_ConnectionWrapper(), None)
    database_module.set_sqlite_pragma(object(), None)


def test_pool_metrics_snapshot_and_peak_property():
    metrics = database_module.PoolHealthMetrics()
    metrics.record_checkout()
    metrics.record_checkout()
    metrics.record_checkin()
    metrics.record_invalidation()
    metrics.record_failed_checkout()

    assert metrics.active_connections == 0
    assert metrics.peak_active_connections == 2
    assert metrics.get_snapshot() == {
        "total_checkouts": 2,
        "total_checkins": 1,
        "total_invalidations": 1,
        "active_connections": 0,
        "peak_active_connections": 2,
        "failed_checkouts": 1,
    }

    snapshot = database_module.get_pool_health_metrics()
    assert set(snapshot) == {
        "total_checkouts",
        "total_checkins",
        "total_invalidations",
        "active_connections",
        "peak_active_connections",
        "failed_checkouts",
    }


def test_build_engine_kwargs_omits_optional_pool_limits():
    current_settings = SimpleNamespace(
        database_url="postgresql+asyncpg://user:pass@example.com/db",  # pragma: allowlist secret
        database_statement_cache_size=0,
        database_pool_size=None,
        database_max_overflow=None,
        database_pool_timeout=30.0,
        database_pool_recycle=600,
    )

    kwargs = database_module._build_engine_kwargs(current_settings)

    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs
    assert kwargs["pool_timeout"] == 30.0
    assert kwargs["pool_recycle"] == 600


def test_build_engine_kwargs_contracts_sqlite_and_postgres_defaults():
    sqlite_kwargs = database_module._build_engine_kwargs(
        SimpleNamespace(database_url="sqlite+aiosqlite:///./local.db")
    )
    assert sqlite_kwargs == {
        "pool_pre_ping": True,
        "echo": False,
        "poolclass": database_module.NullPool,
        "connect_args": {"timeout": 30.0},
    }

    postgres_kwargs = database_module._build_engine_kwargs(
        SimpleNamespace(
            database_url="postgresql+asyncpg://db.example/university",
            database_statement_cache_size=1024,
            database_pool_size=8,
            database_max_overflow=4,
            database_pool_timeout=30.0,
            database_pool_recycle=540,
        )
    )
    assert postgres_kwargs == {
        "pool_pre_ping": True,
        "echo": False,
        "pool_size": 8,
        "max_overflow": 4,
        "pool_timeout": 30.0,
        "pool_recycle": 540,
        "connect_args": {
            "statement_cache_size": 1024,
            "command_timeout": 15.0,
            "server_settings": {"application_name": "university-backend"},
        },
    }


def test_slow_query_logging_truncates_long_statements(monkeypatch):
    slow_logger = MagicMock()
    monkeypatch.setattr(database_module, "slow_query_logger", slow_logger)
    statement = "SELECT " + ("x" * 1595) + "\n"

    database_module._log_slow_query(statement, 501.25, 500.0, True)

    payload = slow_logger.warning.call_args.kwargs["extra"]
    assert payload["statement_length"] == len(statement)
    assert payload["statement"].endswith("...")
    assert len(payload["statement"]) == 1503
    assert payload["executemany"] is True


def test_after_cursor_execute_does_not_log_fast_query(monkeypatch):
    token = database_module._query_start_time.set(100.0)
    try:
        monkeypatch.setattr(database_module.time, "perf_counter", lambda: 100.001)
        monkeypatch.setattr(
            database_module, "settings", SimpleNamespace(slow_query_threshold_ms=500.0)
        )
        log_slow_query = MagicMock()
        monkeypatch.setattr(database_module, "_log_slow_query", log_slow_query)

        database_module._after_cursor_execute(None, None, "SELECT 1", None, None, False)

        log_slow_query.assert_not_called()
        assert database_module._query_start_time.get() is None
    finally:
        database_module._query_start_time.reset(token)


def test_slow_query_logging_closure_handles_fast_and_slow_queries(monkeypatch):
    listeners: dict[str, object] = {}

    monkeypatch.setattr(database_module.event, "contains", lambda *args: False)
    monkeypatch.setattr(
        database_module.event,
        "listen",
        lambda _target, name, callback: listeners.__setitem__(name, callback),
    )
    engine = SimpleNamespace(sync_engine=object())
    current_settings = SimpleNamespace(
        slow_query_logging_enabled=True,
        slow_query_threshold_ms=1.0,
    )

    database_module._setup_slow_query_logging(engine, current_settings)
    after_callback = listeners["after_cursor_execute"]
    assert callable(after_callback)

    monkeypatch.setattr(database_module.time, "perf_counter", lambda: 200.001)
    log_slow_query = MagicMock()
    monkeypatch.setattr(database_module, "_log_slow_query", log_slow_query)
    database_module._query_start_time.set(None)
    after_callback(None, None, "SELECT fast", None, None, False)
    log_slow_query.assert_not_called()

    token = database_module._query_start_time.set(200.0)
    try:
        monkeypatch.setattr(database_module.time, "perf_counter", lambda: 200.0001)
        after_callback(None, None, "SELECT below-threshold", None, None, False)
    finally:
        database_module._query_start_time.reset(token)
    log_slow_query.assert_not_called()

    token = database_module._query_start_time.set(200.0)
    try:
        monkeypatch.setattr(database_module.time, "perf_counter", lambda: 200.01)
        after_callback(None, None, "SELECT slow", None, None, True)
    finally:
        database_module._query_start_time.reset(token)
    call = log_slow_query.call_args
    assert call.args[0] == "SELECT slow"
    assert call.args[1] == pytest.approx(10.0)
    assert call.args[2:] == (1.0, True)


def test_slow_query_logging_disabled_and_zero_threshold_fallback(monkeypatch):
    sync_engine = object()
    listeners: list[tuple[str, object]] = []
    logger = MagicMock()
    monkeypatch.setattr(database_module, "logger", logger)
    monkeypatch.setattr(database_module.event, "contains", lambda *args: False)
    monkeypatch.setattr(
        database_module.event,
        "listen",
        lambda _target, name, callback: listeners.append((name, callback)),
    )

    database_module._setup_slow_query_logging(
        SimpleNamespace(sync_engine=sync_engine),
        SimpleNamespace(slow_query_logging_enabled=False, slow_query_threshold_ms=1),
    )
    assert listeners == []

    database_module._setup_slow_query_logging(
        SimpleNamespace(sync_engine=sync_engine),
        SimpleNamespace(slow_query_logging_enabled=True, slow_query_threshold_ms=0),
    )
    assert [name for name, _callback in listeners] == [
        "before_cursor_execute",
        "after_cursor_execute",
    ]
    with (
        patch.object(database_module.time, "perf_counter", side_effect=[1.0, 1.5]),
        patch.object(database_module, "_log_slow_query") as log_slow_query,
    ):
        before_callback = listeners[0][1]
        after_callback = listeners[1][1]
        before_callback(None, None, "SELECT 1", None, None, False)
        after_callback(None, None, "SELECT 1", None, None, False)

    log_slow_query.assert_called_once_with("SELECT 1", 500.0, 500.0, False)
    logger.info.assert_called_once_with(
        "Slow query logging enabled", threshold_ms=500.0
    )


def test_cursor_start_and_pool_callbacks_skip_debug_logging(monkeypatch):
    database_module._before_cursor_execute(None, None, "SELECT 1", None, None, False)
    assert database_module._query_start_time.get() is not None
    database_module._query_start_time.set(None)

    monkeypatch.setattr(database_module, "is_logger_enabled", lambda *_args: False)
    database_module._on_checkout(None, None, None)
    database_module._on_checkin(None, None)


def test_pool_monitoring_registers_optional_checkout_failed(monkeypatch):
    events: list[str] = []
    pool = SimpleNamespace(
        dispatch=SimpleNamespace(checkout_failed=object()),
        size=lambda: 4,
        overflow=lambda: 1,
    )
    engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))

    monkeypatch.setattr(
        database_module.event,
        "listen",
        lambda _target, name, _callback: events.append(name),
    )
    database_module._setup_pool_health_monitoring(engine)

    assert events == ["checkout", "checkin", "invalidate", "checkout_failed"]


def test_pool_monitoring_uses_na_for_pools_without_size_or_overflow(monkeypatch):
    events: list[str] = []
    pool = SimpleNamespace(dispatch=SimpleNamespace())
    engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))
    logger = MagicMock()

    monkeypatch.setattr(database_module, "logger", logger)
    monkeypatch.setattr(
        database_module.event,
        "listen",
        lambda _target, name, _callback: events.append(name),
    )

    database_module._setup_pool_health_monitoring(engine)

    assert events == ["checkout", "checkin", "invalidate"]
    logger.info.assert_called_once_with(
        "Pool health monitoring enabled (size=%s, overflow=%s)", "N/A", "N/A"
    )


def test_create_session_factory_configures_primary_and_read_replica(monkeypatch):
    primary = SimpleNamespace()
    replica = SimpleNamespace()
    create_engine = MagicMock(side_effect=[primary, replica])
    setup_pool = MagicMock()
    session_factory = object()
    make_session = MagicMock(return_value=session_factory)
    monkeypatch.setattr(database_module, "create_async_engine", create_engine)
    monkeypatch.setattr(database_module, "_setup_pool_health_monitoring", setup_pool)
    monkeypatch.setattr(database_module, "async_sessionmaker", make_session)

    current_settings = SimpleNamespace(
        database_url="sqlite+aiosqlite:///./primary.db",
        database_read_replica_url="sqlite+aiosqlite:///./replica.db",
        slow_query_logging_enabled=False,
    )

    result = database_module.create_session_factory(current_settings)

    assert result == (primary, session_factory, replica)
    assert [entry.args[0] for entry in create_engine.call_args_list] == [
        current_settings.database_url,
        current_settings.database_read_replica_url,
    ]
    assert create_engine.call_args_list[0].kwargs == {
        "pool_pre_ping": True,
        "echo": False,
        "poolclass": database_module.NullPool,
        "connect_args": {"timeout": 30.0},
    }
    setup_pool.assert_has_calls([call(primary), call(replica)])
    make_session.assert_called_once_with(
        primary,
        expire_on_commit=False,
        class_=database_module.AsyncSession,
    )


def test_pool_callbacks_emit_debug_logs(monkeypatch):
    pool_logger = MagicMock()
    monkeypatch.setattr(database_module, "pool_health_logger", pool_logger)
    monkeypatch.setattr(database_module, "is_logger_enabled", lambda *_args: True)

    database_module._on_checkout(None, None, None)
    database_module._on_checkin(None, None)

    assert pool_logger.debug.call_count == 2


def test_lazy_proxy_reports_initialization_failure(monkeypatch):
    monkeypatch.setattr(database_module, "init_database", lambda: None)
    proxy = database_module._LazyProxy(lambda: None, "broken")

    with pytest.raises(RuntimeError, match="Database broken could not be initialized"):
        _ = proxy.some_attribute
    assert repr(proxy) == "<_LazyProxy for broken (uninitialized)>"
    with pytest.raises(RuntimeError, match="Database broken could not be initialized"):
        bool(proxy)


def test_init_database_rechecks_state_inside_lock(monkeypatch):
    sentinel = object()

    class _Lock:
        def __enter__(self):
            database_module._engine = sentinel
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(database_module, "_engine", None)
    monkeypatch.setattr(database_module, "_init_lock", _Lock())
    create_factory = MagicMock()
    monkeypatch.setattr(database_module, "create_session_factory", create_factory)

    database_module.init_database()

    create_factory.assert_not_called()


def test_init_database_initializes_replica_read_factory_and_masks_urls(monkeypatch):
    primary = object()
    replica = object()
    read_factory = object()
    current_settings = SimpleNamespace(
        database_url="postgresql+asyncpg://user:secret@db.example/university",
        database_read_replica_url=(
            "postgresql+asyncpg://user:secret@replica.example/university"
        ),
    )
    create_factory = MagicMock(return_value=(primary, object(), replica))
    make_session = MagicMock(return_value=read_factory)
    tenant_listeners = MagicMock()
    logger = MagicMock()

    monkeypatch.setattr(database_module, "_engine", None)
    monkeypatch.setattr(database_module, "_async_session", None)
    monkeypatch.setattr(database_module, "_read_replica_engine", None)
    monkeypatch.setattr(database_module, "_read_session_factory", None)
    monkeypatch.setattr(database_module, "create_session_factory", create_factory)
    monkeypatch.setattr(database_module, "async_sessionmaker", make_session)
    monkeypatch.setattr(database_module, "logger", logger)

    with patch(
        "app.core.db.listeners.register_tenant_listeners", tenant_listeners
    ):
        database_module.init_database(current_settings)

    create_factory.assert_called_once_with(current_settings)
    make_session.assert_called_once_with(
        replica,
        expire_on_commit=False,
        class_=database_module.AsyncSession,
    )
    tenant_listeners.assert_called_once_with()
    assert database_module.get_read_engine() is replica
    logger.info.assert_called_once_with(
        "Database initialised: %s (replica: %s)",
        "db.example/university",
        "replica.example/university",
    )


def test_get_read_engine_falls_back_to_primary(monkeypatch):
    primary = object()
    monkeypatch.setattr(database_module, "_read_replica_engine", None)
    monkeypatch.setattr(database_module, "_engine", primary)

    assert database_module.get_read_engine() is primary


@pytest.mark.asyncio
async def test_get_db_yields_and_closes_session(monkeypatch):
    session = object()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(database_module, "async_session", lambda: context)

    generator = database_module.get_db()
    assert await anext(generator) is session
    await generator.aclose()
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_db_returns_after_successful_connection(monkeypatch):
    connection = SimpleNamespace(execute=AsyncMock())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    engine = SimpleNamespace(connect=lambda: context)
    monkeypatch.setattr(database_module, "engine", engine)

    await database_module.wait_db(max_attempts=1)

    connection.execute.assert_awaited_once()
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_db_with_zero_attempts_returns_without_connection(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(database_module, "engine", SimpleNamespace(connect=connect))

    await database_module.wait_db(max_attempts=0)

    connect.assert_not_called()
