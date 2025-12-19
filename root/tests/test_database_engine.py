from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.core import database as database_module


@pytest.fixture(autouse=True)
def prepare_database():  # type: ignore[override]
    yield


@pytest.fixture(autouse=True)
def clean_database():  # type: ignore[override]
    yield


@pytest.fixture(autouse=True)
def configure_rate_limit():  # type: ignore[override]
    yield


@pytest.fixture(autouse=True)
def notification_queue_shutdown():  # type: ignore[override]
    yield


@pytest.mark.asyncio
async def test_create_session_factory_uses_null_pool_for_development(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured["engine_kwargs"] = kwargs
        # Mock engine needs sync_engine for slow query logging setup
        return SimpleNamespace(sync_engine=SimpleNamespace())

    def fake_sessionmaker(engine, **kwargs):
        captured["engine"] = engine
        captured["session_kwargs"] = kwargs
        return "session"

    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(database_module, "async_sessionmaker", fake_sessionmaker)
    # Avoid failures in _setup_slow_query_logging which is called during
    # factory creation
    monkeypatch.setattr(database_module.event, "listen", lambda *args, **kwargs: None)

    stub_settings = SimpleNamespace(
        database_url="sqlite+aiosqlite:///./local.db",
        is_development=True,
        database_pool_size=7,
        database_max_overflow=3,
        database_pool_timeout=25.0,
        database_pool_recycle=600,
    )

    engine, session_factory = database_module.create_session_factory(stub_settings)

    assert hasattr(engine, "sync_engine")
    assert session_factory == "session"
    assert captured["url"] == "sqlite+aiosqlite:///./local.db"
    engine_kwargs = captured["engine_kwargs"]
    assert engine_kwargs["pool_pre_ping"] is True
    assert engine_kwargs["echo"] is False
    assert engine_kwargs["poolclass"] is database_module.NullPool
    assert "pool_size" not in engine_kwargs
    assert "max_overflow" not in engine_kwargs
    assert "pool_timeout" not in engine_kwargs
    assert "pool_recycle" not in engine_kwargs
    assert captured["engine"] == engine
    assert captured["session_kwargs"] == {
        "expire_on_commit": False,
        "class_": database_module.AsyncSession,
    }


@pytest.mark.asyncio
async def test_create_session_factory_uses_pool_settings_for_production(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured["engine_kwargs"] = kwargs
        return "engine"

    def fake_sessionmaker(engine, **kwargs):
        captured["engine"] = engine
        captured["session_kwargs"] = kwargs
        return "session"

    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(database_module, "async_sessionmaker", fake_sessionmaker)

    stub_settings = SimpleNamespace(
        database_url="postgresql+asyncpg://user:pass@example.com/db",
        is_development=False,
        database_pool_size=8,
        database_max_overflow=4,
        database_pool_timeout=45.0,
        database_pool_recycle=900,
    )

    engine, session_factory = database_module.create_session_factory(stub_settings)

    assert engine == "engine"
    assert session_factory == "session"
    assert captured["url"] == "postgresql+asyncpg://user:pass@example.com/db"
    engine_kwargs = captured["engine_kwargs"]
    assert engine_kwargs == {
        "pool_pre_ping": True,
        "echo": False,
        "pool_size": 8,
        "max_overflow": 4,
        "pool_timeout": 45.0,
        "pool_recycle": 900,
    }
    assert captured["engine"] == "engine"
    assert captured["session_kwargs"] == {
        "expire_on_commit": False,
        "class_": database_module.AsyncSession,
    }


@pytest.mark.asyncio
async def test_wait_db_logs_final_error_and_raises_cause(monkeypatch, caplog):
    attempts: list[int] = []

    class _FailingConnection:
        async def __aenter__(self):
            attempts.append(1)
            raise RuntimeError("transient outage")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FailingEngine:
        def connect(self):
            return _FailingConnection()

    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(database_module, "engine", _FailingEngine())
    monkeypatch.setattr(database_module.asyncio, "sleep", _fake_sleep)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError) as excinfo:
            await database_module.wait_db(max_attempts=2, delay=0.25)

    assert "Database connection failed after 2 attempts: transient outage" in str(excinfo.value)
    # Sleep is only performed between attempts, not after the final failure.
    assert sleep_calls == [0.25]

    error_logs = [record for record in caplog.records if record.levelname in {"WARNING", "ERROR"}]
    assert any(
        record.levelname == "WARNING" and "attempt 1/2" in record.getMessage()
        for record in error_logs
    )
    assert any(
        record.levelname == "ERROR"
        and "attempt 2/2" in record.getMessage()
        and "transient outage" in record.getMessage()
        for record in error_logs
    )


def test_after_cursor_execute_handles_no_start_time():
    """Verify that _after_cursor_execute handles missing start time gracefully."""
    from app.core.database import _after_cursor_execute, _query_start_time

    # Ensure start time is None
    token = _query_start_time.set(None)
    try:
        # Should return early without error
        _after_cursor_execute(None, None, "SELECT 1", None, None, False)
        assert _query_start_time.get() is None
    finally:
        _query_start_time.reset(token)
