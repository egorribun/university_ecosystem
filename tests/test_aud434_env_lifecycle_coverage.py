"""Exercise Alembic environment configuration without opening a database."""

from __future__ import annotations

import importlib.util
import logging.config
import sys
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_asyncio
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy import pool

import app.core.db.retained_table_metadata as retained_table_metadata
import app.core.db.schema_drift as schema_drift
import app.core.migration_settings as migration_settings
from alembic import context as alembic_context
from alembic import op as alembic_op

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "alembic" / "env.py"
INI_PATH = ROOT / "alembic.ini"
ENV_MODULE_NAME = "aud434_candidate_alembic_env"
PLUGIN_MODULE_NAME = "app.core.db.alembic_json_server_defaults"


def _new_config(url: str) -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _patch_import_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "file_config": [],
        "resolve_url": [],
        "load_settings": [],
        "metadata": [],
        "include_object": [],
        "plugin_register": [],
    }
    settings = object()
    metadata = object()
    include_object = object()

    def file_config(filename: str, **kwargs: Any) -> None:
        calls["file_config"].append((filename, kwargs))

    def load_settings() -> object:
        calls["load_settings"].append(True)
        return settings

    def resolve_url(value: object, *, ini_url: str | None = None) -> str:
        calls["resolve_url"].append((value, ini_url))
        return url

    def build_metadata(_source: Any, *, dialect_name: str) -> object:
        calls["metadata"].append(dialect_name)
        return metadata

    def build_include_object(connection: Any) -> object:
        calls["include_object"].append(connection)
        return include_object

    def register_plugin() -> None:
        calls["plugin_register"].append(True)

    plugin = ModuleType(PLUGIN_MODULE_NAME)
    monkeypatch.setattr(plugin, "register", register_plugin, raising=False)

    monkeypatch.setattr(logging.config, "fileConfig", file_config)
    monkeypatch.setattr(migration_settings, "load_migration_settings", load_settings)
    monkeypatch.setattr(migration_settings, "resolve_migration_url", resolve_url)
    monkeypatch.setattr(
        retained_table_metadata, "build_migration_metadata", build_metadata
    )
    monkeypatch.setattr(
        schema_drift, "build_partition_aware_include_object", build_include_object
    )
    monkeypatch.setitem(sys.modules, PLUGIN_MODULE_NAME, plugin)
    calls["metadata_value"] = metadata
    calls["include_object_value"] = include_object
    calls["settings_value"] = settings
    return calls


@contextmanager
def _load_environment(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    *,
    as_sql: bool,
) -> Iterator[ModuleType]:
    script = ScriptDirectory.from_config(config)
    with EnvironmentContext(config, script, as_sql=as_sql):
        spec = importlib.util.spec_from_file_location(ENV_MODULE_NAME, ENV_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, ENV_MODULE_NAME, module)
        try:
            spec.loader.exec_module(module)
            yield module
        finally:
            monkeypatch.delitem(sys.modules, ENV_MODULE_NAME, raising=False)


class _OfflineBind:
    def __init__(self, results: list[Any]) -> None:
        self.results = iter(results)

    def execute(self, _statement: Any) -> Any:
        return next(self.results)


class _SyncEngine:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.connect_calls = 0
        self.enter_calls = 0
        self.exit_calls = 0

    def connect(self) -> _SyncEngine:
        self.connect_calls += 1
        return self

    def __enter__(self) -> Any:
        self.enter_calls += 1
        return self.connection

    def __exit__(self, *_exc: Any) -> None:
        self.exit_calls += 1


class _AsyncConnection:
    def __init__(self, sync_connection: Any) -> None:
        self.sync_connection = sync_connection
        self.run_sync_calls = 0

    async def run_sync(self, callback: Any) -> Any:
        self.run_sync_calls += 1
        return callback(self.sync_connection)


class _AsyncConnectionContext:
    def __init__(self, connection: _AsyncConnection) -> None:
        self.connection = connection
        self.enter_calls = 0
        self.exit_calls = 0

    async def __aenter__(self) -> _AsyncConnection:
        self.enter_calls += 1
        return self.connection

    async def __aexit__(self, *_exc: Any) -> None:
        self.exit_calls += 1


class _AsyncEngine:
    def __init__(self, connection_context: _AsyncConnectionContext) -> None:
        self.connection_context = connection_context
        self.connect_calls = 0
        self.dispose_calls = 0

    def connect(self) -> _AsyncConnectionContext:
        self.connect_calls += 1
        return self.connection_context

    async def dispose(self) -> None:
        self.dispose_calls += 1


def test_offline_sql_uses_temporary_inspection_and_bind_shims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "sqlite:///aud434-offline-render-only.db"
    calls = _patch_import_dependencies(monkeypatch, url)
    config = _new_config(url)
    config_calls: list[dict[str, Any]] = []
    run_calls: list[bool] = []
    marker = object()
    offline_bind = _OfflineBind([None, marker])
    current_bind: list[Any] = [offline_bind]

    def get_bind(*_args: Any, **_kwargs: Any) -> Any:
        return current_bind[0]

    monkeypatch.setattr(alembic_op, "get_bind", get_bind)
    monkeypatch.setattr(
        alembic_context, "configure", lambda **kwargs: config_calls.append(kwargs)
    )
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)

    def run_migrations() -> None:
        module = sys.modules[ENV_MODULE_NAME]
        inspector = sa.inspect(object())
        assert isinstance(inspector, module._OfflineInspector)
        assert inspector.clear_cache() is None
        assert inspector.get_table_names(schema="public") == []
        assert inspector.has_table("events") is True
        assert inspector.get_columns("events") == []
        assert inspector.get_indexes("events") == []
        assert inspector.get_foreign_keys("events") == []
        assert inspector.get_unique_constraints("events") == []
        assert inspector.get_check_constraints("events") == []
        assert inspector.get_table_options("events") == {}
        assert inspector.get_pk_constraint("events") == {"constrained_columns": []}

        result = alembic_op.get_bind().execute("SELECT 1")
        assert isinstance(result, module._OfflineResult)
        assert result.fetchone() is None
        assert result.fetchall() == []
        assert result.scalar() is None
        assert result.first() is None
        assert list(result) == []
        assert alembic_op.get_bind().execute("SELECT 2") is marker
        run_calls.append(True)
        raise BrokenPipeError("offline SQL output consumer closed")

    monkeypatch.setattr(alembic_context, "run_migrations", run_migrations)
    original_inspect = sa.inspect

    with _load_environment(monkeypatch, config, as_sql=True) as module:
        assert run_calls == [True]
        assert len(config_calls) == 1
        assert config_calls[0]["url"] == url
        assert config_calls[0]["literal_binds"] is True
        assert config_calls[0]["target_metadata"] is calls["metadata_value"]
        assert calls["metadata"] == ["sqlite"]
        assert calls["file_config"] == [
            (str(INI_PATH), {"disable_existing_loggers": False})
        ]
        assert calls["resolve_url"] == [(calls["settings_value"], url)]
        assert calls["load_settings"] == [True]
        assert calls["plugin_register"] == []
        assert sa.inspect is original_inspect
        assert alembic_op.get_bind is get_bind

        no_execute = SimpleNamespace()
        current_bind[0] = no_execute
        assert module._offline_get_bind() is no_execute

        already_wrapped = SimpleNamespace(
            _wrapped_for_offline=True, execute=lambda _statement: None
        )
        current_bind[0] = already_wrapped
        assert module._offline_get_bind() is already_wrapped

        current_bind[0] = None
        assert module._offline_get_bind() is None

        online_bind = SimpleNamespace(execute=lambda _statement: None)
        current_bind[0] = online_bind
        with monkeypatch.context() as scoped:
            scoped.setattr(module.context, "is_offline_mode", lambda: False)
            assert module._offline_get_bind() is online_bind
            assert not hasattr(online_bind, "_wrapped_for_offline")
            with pytest.raises(sa.exc.NoInspectionAvailable):
                module._offline_inspect(object())


def test_sync_engine_configuration_closes_its_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql+psycopg://localhost/test"
    calls = _patch_import_dependencies(monkeypatch, url)
    config = _new_config(url)
    configured: list[dict[str, Any]] = []
    migration_calls: list[bool] = []
    connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    engine = _SyncEngine(connection)
    factory_calls: list[tuple[dict[str, Any], str, Any]] = []

    def engine_factory(
        options: dict[str, Any], *, prefix: str, poolclass: Any
    ) -> _SyncEngine:
        factory_calls.append((options, prefix, poolclass))
        return engine

    monkeypatch.setattr(sa, "engine_from_config", engine_factory)
    monkeypatch.setattr(
        alembic_context, "configure", lambda **kwargs: configured.append(kwargs)
    )
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)
    monkeypatch.setattr(
        alembic_context, "run_migrations", lambda: migration_calls.append(True)
    )

    with _load_environment(monkeypatch, config, as_sql=False):
        assert engine.connect_calls == 1
        assert engine.enter_calls == 1
        assert engine.exit_calls == 1
        assert factory_calls == [
            ({"sqlalchemy.url": url}, "sqlalchemy.", pool.NullPool)
        ]
        assert len(configured) == 1
        assert configured[0]["connection"] is connection
        assert configured[0]["compare_server_default"] is True
        assert configured[0]["target_metadata"] is calls["metadata_value"]
        assert configured[0]["include_object"] is calls["include_object_value"]
        assert calls["metadata"] == ["postgresql"]
        assert calls["include_object"] == [connection]
        assert calls["plugin_register"] == [True]
        assert calls["resolve_url"] == [(calls["settings_value"], url)]
        assert migration_calls == [True]


def test_async_engine_configuration_disposes_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql+asyncpg://localhost/test"
    calls = _patch_import_dependencies(monkeypatch, url)
    config = _new_config(url)
    configured: list[dict[str, Any]] = []
    migration_calls: list[bool] = []
    sync_connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    async_connection = _AsyncConnection(sync_connection)
    connection_context = _AsyncConnectionContext(async_connection)
    engine = _AsyncEngine(connection_context)
    factory_calls: list[tuple[dict[str, Any], str, Any]] = []

    def engine_factory(
        options: dict[str, Any], *, prefix: str, poolclass: Any
    ) -> _AsyncEngine:
        factory_calls.append((options, prefix, poolclass))
        return engine

    monkeypatch.setattr(sa_asyncio, "async_engine_from_config", engine_factory)
    monkeypatch.setattr(
        alembic_context, "configure", lambda **kwargs: configured.append(kwargs)
    )
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)
    monkeypatch.setattr(
        alembic_context, "run_migrations", lambda: migration_calls.append(True)
    )

    with _load_environment(monkeypatch, config, as_sql=False):
        assert engine.connect_calls == 1
        assert connection_context.enter_calls == 1
        assert connection_context.exit_calls == 1
        assert async_connection.run_sync_calls == 1
        assert engine.dispose_calls == 1
        assert factory_calls == [
            ({"sqlalchemy.url": url}, "sqlalchemy.", pool.NullPool)
        ]
        assert len(configured) == 1
        assert configured[0]["connection"] is sync_connection
        assert configured[0]["compare_server_default"] is True
        assert calls["metadata"] == ["postgresql"]
        assert calls["include_object"] == [sync_connection]
        assert calls["plugin_register"] == [True]
        assert migration_calls == [True]


def test_async_engine_disposes_when_migration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql+asyncpg://localhost/test"
    _patch_import_dependencies(monkeypatch, url)
    config = _new_config(url)
    sync_connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    async_connection = _AsyncConnection(sync_connection)
    connection_context = _AsyncConnectionContext(async_connection)
    engine = _AsyncEngine(connection_context)

    monkeypatch.setattr(
        sa_asyncio,
        "async_engine_from_config",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr(alembic_context, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)

    def fail_migrations() -> None:
        raise RuntimeError("migration callback failed")

    monkeypatch.setattr(alembic_context, "run_migrations", fail_migrations)

    with pytest.raises(RuntimeError, match="migration callback failed"):
        with _load_environment(monkeypatch, config, as_sql=False):
            pytest.fail("failed migration unexpectedly completed")

    assert engine.connect_calls == 1
    assert connection_context.enter_calls == 1
    assert connection_context.exit_calls == 1
    assert engine.dispose_calls == 1
