from __future__ import annotations

import asyncio
import logging
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Table, inspect
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.models.models import PushSubscription

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

_async_ready = False
_async_lock = asyncio.Lock()
_sync_ready = False
_sync_lock = Lock()

logger = logging.getLogger(__name__)


def _create_schema(bind: Connection | Engine) -> None:
    PushSubscription.metadata.create_all(
        bind=bind, tables=[cast(Table, PushSubscription.__table__)]
    )


def _ensure_columns(bind: Connection) -> None:
    table_name = PushSubscription.__tablename__
    inspector = inspect(bind)
    tables = {name for name in inspector.get_table_names()}
    if table_name not in tables:
        _create_schema(bind)
        inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns(table_name)}
    preparer = bind.dialect.identifier_preparer

    def _add_column(
        column: Any, *, default_sql: str | None = None, not_null: bool = False
    ) -> None:
        column_name = preparer.quote(column.name)
        type_sql = column.type.compile(bind.dialect)
        parts = [column_name, type_sql]
        if default_sql:
            parts.append(f"DEFAULT {default_sql}")
        if not_null:
            parts.append("NOT NULL")
        statement = (
            f"ALTER TABLE {preparer.quote(table_name)} ADD COLUMN {' '.join(parts)}"
        )
        bind.exec_driver_sql(statement)

    if "user_agent" not in columns:
        _add_column(PushSubscription.__table__.c.user_agent)
    if "last_seen_at" not in columns:
        _add_column(PushSubscription.__table__.c.last_seen_at)
    if "created_at" not in columns:
        created_at_col = PushSubscription.__table__.c.created_at
        default_clause = created_at_col.server_default
        default_sql = None
        if default_clause is not None:
            default_sql = str(default_clause.arg.compile(dialect=bind.dialect))
        _add_column(created_at_col, default_sql=default_sql, not_null=True)
    if "topics" not in columns:
        if bind.dialect.name.startswith("postgresql"):
            default_expr = "'[]'::jsonb"
        else:
            default_expr = "'[]'"
        _add_column(
            PushSubscription.__table__.c.topics,
            default_sql=default_expr,
            not_null=True,
        )


async def ensure_push_subscription_schema(db: AsyncSession) -> None:
    global _async_ready, _sync_ready
    if _async_ready:
        return
    async with _async_lock:
        if _async_ready:
            return  # type: ignore[unreachable]

        try:

            def _sync_create(sync_session: Any) -> None:
                connection = sync_session.connection()
                _ensure_columns(connection)

            await db.run_sync(_sync_create)
        except SQLAlchemyError:
            logger.exception(
                "Failed to ensure push subscription schema using async session"
            )
            return
        else:
            _async_ready = True
            _sync_ready = True


def ensure_push_subscription_schema_sync(engine: Engine | None) -> None:
    global _sync_ready, _async_ready
    if engine is None or _sync_ready:
        return
    with _sync_lock:
        if _sync_ready:
            return  # type: ignore[unreachable]
        try:
            with engine.connect() as connection:
                _ensure_columns(connection)
        except OperationalError as exc:
            logger.warning(
                (
                    "Push subscription schema creation skipped; "
                    "database is unavailable: %s"
                ),
                exc,
                exc_info=False,
            )
            return
        except SQLAlchemyError:
            logger.exception(
                "Failed to ensure push subscription schema using sync engine"
            )
            return
        else:
            _sync_ready = True
            _async_ready = True
