from __future__ import annotations

import asyncio
import functools
import os
import sys
from logging.config import fileConfig
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url, Engine
from sqlalchemy.ext.asyncio import async_engine_from_config, AsyncEngine
from sqlalchemy.engine.base import Connection as SyncConnection

from alembic import context
from alembic.config import Config

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.db.schema_drift import (
    build_partition_aware_include_object,
    filter_check_backed_nullable_diffs,
)
from app.core.migration_settings import (
    MigrationSettings,
    load_migration_settings,
    resolve_migration_url,
    should_skip_development_migration,
)
import app.models as models
from app.core.db.retained_table_metadata import build_migration_metadata


if TYPE_CHECKING:
    from app.core.config import Settings


@functools.cache
def _migration_settings() -> MigrationSettings:
    """Resolve the DB-only view once for this Alembic environment run."""
    return load_migration_settings()


@functools.cache
def _settings() -> Settings:
    """Return migration-tolerant settings, built only when a run needs them.

    Offline SQL generation with DATABASE_URL configured needs no runtime secrets,
    so validation must not happen while Alembic loads this module.
    """
    from app.core.config import Settings

    return Settings(_allow_missing=True)


config: Config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


class _OfflineInspector:
    """Fallback inspector for Alembic --sql (offline) mode when MockConnection cannot be inspected."""

    def clear_cache(self) -> None:
        """Match SQLAlchemy Inspector; this fallback stores no cache."""
        return None

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


def get_url() -> str:
    # The DB-only view enforces FILE precedence before any ini/default fallback.
    return resolve_migration_url(
        _migration_settings(), ini_url=config.get_main_option("sqlalchemy.url")
    )


def _invoked_command_name() -> str:
    """Return the Alembic CLI command that loaded this environment, or "" if none did."""
    command_spec = getattr(config.cmd_opts, "cmd", None)
    if not command_spec:
        return ""
    return str(getattr(command_spec[0], "__name__", ""))


def _development_fallback_skip_allowed() -> bool:
    """Allow a skip only for CLI ``upgrade`` with the local SQLite default in development.

    ``check``, ``current``, ``downgrade`` and programmatic callers never skip: each would
    exit 0 without examining the schema it was asked about.
    """
    if _invoked_command_name() != "upgrade":
        return False
    return should_skip_development_migration(
        development_fallback_fields=_settings().development_fallback_fields,
        environment=os.getenv("ENVIRONMENT") or "",
        explicit_target=(
            bool(config.get_main_option("sqlalchemy.url"))
            or config.attributes.get("connection") is not None
        ),
    )


def run_migrations_offline() -> None:
    # Without an explicit URL, get_url() would render SQL for the local SQLite default,
    # which is not a PostgreSQL migration artifact. Refuse instead of rendering it.
    if _migration_settings().has_development_fallbacks and not config.get_main_option(
        "sqlalchemy.url"
    ):
        raise RuntimeError(
            "Refusing to render Alembic SQL: development fallbacks are active for "
            "database_url. Set DATABASE_URL explicitly."
        )
    url: str = get_url()
    context.configure(
        url=url,
        target_metadata=build_migration_metadata(
            models.Base.metadata, dialect_name=make_url(url).get_backend_name()
        ),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        transactional_ddl=True,
        transaction_per_migration=True,
        process_revision_directives=filter_check_backed_nullable_diffs,
    )

    # Keep these offline compatibility shims scoped to the migration run. They
    # replace process-global APIs and must not affect later Alembic contexts.
    previous_inspect = sa.inspect
    previous_get_bind = _alembic_op.get_bind
    try:
        sa.inspect = _offline_inspect
        _alembic_op.get_bind = _offline_get_bind
        with context.begin_transaction():
            context.run_migrations()
    finally:
        sa.inspect = previous_inspect
        _alembic_op.get_bind = previous_get_bind


def _configure_context(connection: SyncConnection) -> None:
    context.configure(
        connection=connection,
        target_metadata=build_migration_metadata(
            models.Base.metadata, dialect_name=connection.dialect.name
        ),
        include_object=build_partition_aware_include_object(connection),
        compare_type=True,
        # AUD-434: `alembic check` must also compare server defaults.
        compare_server_default=True,
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
    # AUD-168 (audit 2026-10): only the documented local SQLite default may skip,
    # and only in a development environment. Every other development fallback
    # fails closed, because exit 0 without migrating looks like a successful deploy.
    if _settings().has_development_fallbacks:
        if not _development_fallback_skip_allowed():
            fallback_fields = ", ".join(_settings().development_fallback_fields)
            raise RuntimeError(
                "Refusing to skip Alembic migrations: development fallbacks are "
                f"active for {fallback_fields}. Set DATABASE_URL and every "
                "required secret explicitly."
            )
        import warnings

        warnings.warn(
            "Skipping Alembic migrations: has_development_fallbacks is True. "
            "Schema drift may cause runtime errors. "
            "Set DATABASE_URL and SECRET_KEY explicitly to run migrations.",
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
