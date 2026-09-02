import asyncio
import os
import sys
from logging.config import fileConfig
from typing import Any

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url, Engine
from sqlalchemy.ext.asyncio import async_engine_from_config, AsyncEngine
from sqlalchemy.engine.base import Connection as SyncConnection

from alembic import context
from alembic.config import Config

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.quality.alembic_schema_drift import (
    build_partition_aware_include_object,
    filter_check_backed_nullable_diffs,
)
from app.core.config import Settings
import app.models as models

_settings = Settings(_allow_missing=True)
config: Config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata


class _OfflineInspector:
    """Fallback inspector for Alembic --sql (offline) mode when MockConnection cannot be inspected."""

    def get_table_names(self, schema: str | None = None) -> list[str]:
        return []

    def has_table(self, table_name: str, schema: str | None = None) -> bool:
        return True

    def get_columns(
        self, table_name: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_indexes(
        self, table_name: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_foreign_keys(
        self, table_name: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_unique_constraints(
        self, table_name: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_check_constraints(
        self, table_name: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_table_options(
        self, table_name: str, schema: str | None = None
    ) -> dict[str, Any]:
        return {}

    def get_pk_constraint(
        self, table_name: str, schema: str | None = None
    ) -> dict[str, Any]:
        return {"constrained_columns": []}


_orig_inspect = sa.inspect


def _offline_inspect(subject: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return _orig_inspect(subject, *args, **kwargs)
    except sa.exc.NoInspectionAvailable:
        if context.is_offline_mode():
            return _OfflineInspector()
        raise


sa.inspect = _offline_inspect


class _OfflineResult:
    """Mock result object for op.get_bind().execute() in Alembic offline mode."""

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []

    def scalar(self) -> None:
        return None

    def first(self) -> None:
        return None

    def __iter__(self) -> Any:
        return iter([])


from alembic import op as _alembic_op

_orig_get_bind = _alembic_op.get_bind


def _offline_get_bind(*args: Any, **kwargs: Any) -> Any:
    bind = _orig_get_bind(*args, **kwargs)
    if (
        context.is_offline_mode()
        and bind is not None
        and not hasattr(bind, "_wrapped_for_offline")
    ):
        orig_execute = getattr(bind, "execute", None)
        if orig_execute:

            def _wrapped_execute(*exec_args: Any, **exec_kwargs: Any) -> Any:
                res = orig_execute(*exec_args, **exec_kwargs)
                if res is None:
                    return _OfflineResult()
                return res

            bind.execute = _wrapped_execute
            bind._wrapped_for_offline = True
    return bind


_alembic_op.get_bind = _offline_get_bind


def get_url() -> str:
    env_url = os.getenv("DATABASE_URL", "")
    if env_url:
        return env_url
    if _settings.database_url:
        return _settings.database_url
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    raise RuntimeError("Database URL is not configured for Alembic")


def run_migrations_offline() -> None:
    url: str = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        transactional_ddl=True,
        transaction_per_migration=True,
        process_revision_directives=filter_check_backed_nullable_diffs,
    )
    with context.begin_transaction():
        context.run_migrations()


def _configure_context(connection: SyncConnection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=build_partition_aware_include_object(connection),
        compare_type=True,
        render_as_batch=True,
        transactional_ddl=True,
        transaction_per_migration=True,
        process_revision_directives=filter_check_backed_nullable_diffs,
    )


def run_migrations_online() -> None:
    url: str = get_url()
    config_options: dict[str, Any] = {"sqlalchemy.url": url}
    url_obj = make_url(url)

    # RZ-W18-06 (audit 2026-03-23 Wave 18): emit a proper Python warning instead
    # of a bare print(). Previously the silent skip was easily missed in logs,
    # leading developers to unknowingly accumulate schema drift.
    if _settings.has_development_fallbacks:
        import warnings

        warnings.warn(
            "Skipping Alembic migrations: has_development_fallbacks is True. "
            "Schema drift may cause runtime errors. "
            "Set DATABASE_URL explicitly to run migrations.",
            stacklevel=2,
        )
        return

    def run_sync_migrations(connection: SyncConnection) -> None:
        _configure_context(connection)
        with context.begin_transaction():
            context.run_migrations()

    connection: Any = config.attributes.get("connection")
    if connection:
        # Connection injected externally (e.g., from a test fixture).
        run_sync_migrations(connection)
        return

    connectable: Engine | AsyncEngine
    if url_obj.get_dialect().is_async:
        connectable = async_engine_from_config(
            config_options,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        async def async_run_migrations() -> None:
            async with connectable.connect() as connection:
                await connection.run_sync(run_sync_migrations)

        try:
            asyncio.run(async_run_migrations())
        finally:
            asyncio.run(connectable.dispose())
    else:
        connectable = engine_from_config(
            config_options,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            run_sync_migrations(connection)


if context.is_offline_mode():
    try:
        run_migrations_offline()
    except BrokenPipeError:
        pass
else:
    run_migrations_online()
