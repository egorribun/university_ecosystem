import asyncio
import os
import sys
from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url, Engine
from sqlalchemy.ext.asyncio import async_engine_from_config, AsyncEngine
from sqlalchemy.engine.base import Connection as SyncConnection

from alembic import context
from alembic.config import Config

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import Settings
import app.models as models

_settings = Settings(_allow_missing=True)
config: Config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata


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
        transactional_ddl=False,  # Allow non-transactional DDL
    )
    context.run_migrations()


def _configure_context(connection: SyncConnection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
        transactional_ddl=False,  # Allow non-transactional DDL
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
        # P0-05 (audit 2026-03-09): Removed the global `begin_transaction()` wrapper.
        # PostgreSQL commands like `CREATE INDEX CONCURRENTLY` cannot run inside
        # a transaction block. Migrations that require transactions must manage
        # them explicitly or rely on Alembic's per-migration transaction control.
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
            # RZ-12: Use AUTOCOMMIT isolation level for concurrent index support.
            autocommit_engine = connectable.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            async with autocommit_engine.connect() as connection:
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
    run_migrations_offline()
else:
    run_migrations_online()
