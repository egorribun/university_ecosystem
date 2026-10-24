"""Real PostgreSQL notification compatibility reads preserve caller transactions."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import app.api.notifications as notifications_api

_PUBLIC_NOTIFICATION_STATE = """
SELECT c.oid,
       (
           SELECT array_agg(
               a.attname || ':' || a.atttypid::text || ':' || a.atttypmod::text
               ORDER BY a.attnum
           )
           FROM pg_attribute AS a
           WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
       ) AS columns,
       (SELECT count(*) FROM public.notifications) AS row_count
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'notifications'
"""

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL notification fallback",
    ),
]

_COLUMNS = (
    ("id", "UUID PRIMARY KEY"),
    ("user_id", "UUID NOT NULL"),
    ("title", "TEXT NOT NULL"),
    ("title_en", "TEXT"),
    ("body", "TEXT"),
    ("body_en", "TEXT"),
    ("type", "TEXT"),
    ("url", "TEXT"),
    ("created_at", "TIMESTAMPTZ NOT NULL"),
    ("read", "BOOLEAN NOT NULL"),
    ("read_at", "TIMESTAMPTZ"),
)


@pytest_asyncio.fixture
async def notification_transaction(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[AsyncSession, int]]:
    # Reuse the suite's explicit, disposable PostgreSQL service. A connection-bound
    # session also keeps production schema inspection on the temporary-table owner.
    engine = db_session.bind
    assert isinstance(engine, AsyncEngine)
    assert engine.dialect.name == "postgresql", "This proof must not run on SQLite"
    async with engine.connect() as connection:
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            public_state = None
            try:
                await session.execute(text("SET LOCAL statement_timeout = '5s'"))
                await session.execute(text("SET LOCAL search_path TO pg_temp, public"))
                assert (
                    await session.scalar(text("SELECT current_database()"))
                    == engine.url.database
                )
                assert (
                    await session.scalar(
                        text("SELECT to_regclass('pg_temp.notifications')")
                    )
                    is None
                )
                public_state = (
                    await session.execute(text(_PUBLIC_NOTIFICATION_STATE))
                ).one()
                await session.execute(
                    text(
                        "CREATE TEMPORARY TABLE aud343_transaction_probe "
                        "(value INTEGER NOT NULL) ON COMMIT DROP"
                    )
                )
                await session.execute(
                    text("INSERT INTO aud343_transaction_probe VALUES (73)")
                )
                transaction_id = await session.scalar(text("SELECT txid_current()"))
                assert isinstance(transaction_id, int)
                yield session, transaction_id
            finally:
                # Every table/view below is created in this uncommitted transaction.
                # Rollback removes only this test's objects; no public DDL is issued.
                await session.rollback()
                if public_state is not None:
                    unchanged = (
                        await session.execute(text(_PUBLIC_NOTIFICATION_STATE))
                    ).one()
                    assert unchanged == public_state
                    await session.rollback()


async def _create_notifications(
    session: AsyncSession,
    *,
    missing_column: str | None = None,
    failure_source: bool = False,
) -> None:
    definitions = [
        f"{name} {definition}"
        for name, definition in _COLUMNS
        if name != missing_column
    ]
    table_name = "aud343_notification_source" if failure_source else "notifications"
    if failure_source:
        definitions.append("divisor INTEGER NOT NULL DEFAULT 0")
    await session.execute(
        text(
            f"CREATE TEMPORARY TABLE {table_name} "
            f"({', '.join(definitions)}) ON COMMIT DROP"
        )
    )


async def _insert_notification(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    failure_source: bool = False,
) -> uuid.UUID:
    notification_id = uuid.uuid4()
    table_name = "aud343_notification_source" if failure_source else "notifications"
    await session.execute(
        text(
            f"INSERT INTO {table_name} "
            "(id, user_id, title, body, type, url, created_at, read) "
            "VALUES (:id, :user_id, 'Legacy title', 'Legacy body', "
            "'system', '/news', :created_at, false)"
        ),
        {
            "id": notification_id,
            "user_id": user_id,
            "created_at": datetime(2035, 1, 2, 3, 4, 5, tzinfo=UTC),
        },
    )
    return notification_id


async def _assert_outer_work_survives(
    session: AsyncSession, transaction_id: int
) -> None:
    assert await session.scalar(text("SELECT txid_current()")) == transaction_id
    assert (
        await session.scalar(text("SELECT value FROM aud343_transaction_probe")) == 73
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_column", ["title_en", "body_en", "read_at"])
async def test_missing_column_fallback_preserves_postgres_transaction(
    notification_transaction: tuple[AsyncSession, int], missing_column: str
) -> None:
    # Removing the production savepoint leaves PostgreSQL aborted at inspection;
    # rolling back the whole transaction instead destroys the pre-existing work.
    session, transaction_id = notification_transaction
    await _create_notifications(session, missing_column=missing_column)
    user_id = uuid.uuid4()
    notification_id = await _insert_notification(session, user_id)
    await _insert_notification(session, uuid.uuid4())

    rows, available = await notifications_api._fetch_notification_rows(
        session, user_id, 5, None
    )

    assert [row["id"] for row in rows] == [notification_id]
    assert rows[0]["title"] == "Legacy title"
    assert rows[0]["body"] == "Legacy body"
    assert rows[0][missing_column] is None
    assert available is not None
    assert missing_column not in available
    assert {"id", "user_id", "title", "body", "created_at", "read"} <= available
    await _assert_outer_work_survives(session, transaction_id)


@pytest.mark.asyncio
async def test_complete_schema_reads_without_fallback_on_postgres(
    notification_transaction: tuple[AsyncSession, int],
) -> None:
    session, transaction_id = notification_transaction
    await _create_notifications(session)
    user_id = uuid.uuid4()
    notification_id = await _insert_notification(session, user_id)

    rows, available = await notifications_api._fetch_notification_rows(
        session, user_id, 5, None
    )

    assert [row["id"] for row in rows] == [notification_id]
    assert rows[0]["title"] == "Legacy title"
    assert available is None
    await _assert_outer_work_survives(session, transaction_id)


@pytest.mark.asyncio
async def test_unexpected_postgres_error_propagates_without_losing_outer_work(
    notification_transaction: tuple[AsyncSession, int],
) -> None:
    # A real division-by-zero during the production SELECT is not schema drift.
    # Catch-all fallback would hide this error; a missing savepoint poisons the
    # caller's transaction even when the original exception is propagated.
    session, transaction_id = notification_transaction
    await _create_notifications(session, failure_source=True)
    user_id = uuid.uuid4()
    await _insert_notification(session, user_id, failure_source=True)
    await session.execute(
        text(
            "CREATE TEMPORARY VIEW notifications AS "
            "SELECT id, user_id, title, CAST(1 / divisor AS TEXT) AS title_en, "
            "body, body_en, type, url, created_at, read, read_at "
            "FROM aud343_notification_source"
        )
    )

    with pytest.raises(DBAPIError) as failure:
        await notifications_api._fetch_notification_rows(session, user_id, 5, None)

    assert getattr(failure.value.orig, "sqlstate", None) == "22012"
    await _assert_outer_work_survives(session, transaction_id)
