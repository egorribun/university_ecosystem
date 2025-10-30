from __future__ import annotations

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
        return "engine"

    def fake_sessionmaker(engine, **kwargs):
        captured["engine"] = engine
        captured["session_kwargs"] = kwargs
        return "session"

    monkeypatch.setattr(
        database_module, "create_async_engine", fake_create_async_engine
    )
    monkeypatch.setattr(database_module, "async_sessionmaker", fake_sessionmaker)

    stub_settings = SimpleNamespace(
        database_url="sqlite+aiosqlite:///./local.db",
        is_development=True,
        database_pool_size=7,
        database_max_overflow=3,
        database_pool_timeout=25.0,
        database_pool_recycle=600,
    )

    engine, session_factory = database_module.create_session_factory(stub_settings)

    assert engine == "engine"
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
    assert captured["engine"] == "engine"
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

    monkeypatch.setattr(
        database_module, "create_async_engine", fake_create_async_engine
    )
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
