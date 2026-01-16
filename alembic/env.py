import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import Settings
from app.models import models

_settings = Settings(_allow_missing=True)
config = context.config
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
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _configure_context(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )


def run_migrations_online() -> None:
    url = get_url()
    config_options = {"sqlalchemy.url": url}
    url_obj = make_url(url)

    if _settings.has_development_fallbacks:
        print("Skipping Alembic migrations while using development fallback settings.")
        return

    def run_sync_migrations(connection) -> None:
        _configure_context(connection)
        with context.begin_transaction():
            context.run_migrations()

    connection = config.attributes.get("connection")
    if connection:
        print(f"DEBUG: Using injected connection: {connection}")
        run_sync_migrations(connection)
        return

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
    run_migrations_offline()
else:
    run_migrations_online()
