"""PostgreSQL proof for the pgvector startup savepoint (no extension changes)."""

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    event,
    func,
    select,
    table,
    text,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core import lifespan as lifespan_module

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL pgvector startup proof",
    ),
]


@pytest_asyncio.fixture
async def startup_connection(
    db_session: AsyncSession,
) -> AsyncIterator[AsyncConnection]:
    engine = db_session.bind
    assert isinstance(engine, AsyncEngine)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(
                text(
                    "CREATE TEMPORARY TABLE aud389_outer_probe "
                    "(value INTEGER NOT NULL) ON COMMIT DROP"
                )
            )
            await conn.execute(text("INSERT INTO aud389_outer_probe VALUES (389)"))
            yield conn
        finally:
            if transaction.is_active:
                await transaction.rollback()


class _EngineOnOuterTransaction:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        # The application's transaction is a savepoint inside the test-owned
        # outer transaction, so every test-created object is rolled back.
        async with self.conn.begin_nested():
            yield self.conn


def _install_startup_test_environment(
    monkeypatch: pytest.MonkeyPatch,
    conn: AsyncConnection,
    *,
    semantic_search_enabled: bool,
    vector_column: bool,
) -> str:
    name = f"aud389_schema_{uuid.uuid4().hex}"
    metadata = MetaData()
    columns = [Column("id", Integer, primary_key=True)]
    if vector_column:
        columns.append(Column("embedding", Vector(2)))
    Table(name, metadata, *columns, prefixes=["TEMPORARY"], postgresql_on_commit="DROP")
    monkeypatch.setattr(lifespan_module, "engine", _EngineOnOuterTransaction(conn))
    monkeypatch.setattr(lifespan_module, "Base", SimpleNamespace(metadata=metadata))
    monkeypatch.setattr(
        lifespan_module, "runtime_flags", lifespan_module.RuntimeFeatureOverrides()
    )
    monkeypatch.setattr(
        lifespan_module,
        "settings",
        SimpleNamespace(
            auto_create_schema=True,
            environment="production",
            semantic_search_enabled=semantic_search_enabled,
        ),
    )
    return name


async def _missing_extension_name(conn: AsyncConnection) -> str:
    # Use a unique, nonexistent extension rather than dropping or altering vector.
    # PostgreSQL resolves its control file by the same CREATE EXTENSION path.
    name = f"aud389_missing_{uuid.uuid4().hex}"
    assert (
        await conn.scalar(
            text("SELECT count(*) FROM pg_available_extensions WHERE name = :name"),
            {"name": name},
        )
        == 0
    )
    with pytest.raises(DBAPIError) as failure:
        async with conn.begin_nested():
            await conn.exec_driver_sql(f'CREATE EXTENSION "{name}"')
    assert getattr(failure.value.orig, "sqlstate", None) in {"0A000", "58P01"}
    return name


async def _assert_outer_work(conn: AsyncConnection, transaction_id: int) -> None:
    assert await conn.scalar(text("SELECT txid_current()")) == transaction_id
    assert await conn.scalar(text("SELECT value FROM aud389_outer_probe")) == 389


async def test_disabled_search_recovers_after_real_postgres_extension_error(
    startup_connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = startup_connection
    name = _install_startup_test_environment(
        monkeypatch, conn, semantic_search_enabled=False, vector_column=False
    )
    missing = await _missing_extension_name(conn)
    transaction_id = await conn.scalar(text("SELECT txid_current()"))
    assert isinstance(transaction_id, int)
    substitutions: list[tuple[str, str]] = []

    def substitute_extension(_conn, _cursor, statement, parameters, _context, _many):  # type: ignore[no-untyped-def]
        if statement == "CREATE EXTENSION IF NOT EXISTS vector":
            replacement = f'CREATE EXTENSION "{missing}"'
            substitutions.append((statement, replacement))
            return replacement, parameters
        return statement, parameters

    event.listen(
        conn.sync_connection, "before_cursor_execute", substitute_extension, retval=True
    )
    try:
        await lifespan_module._handle_schema_and_extensions()
    finally:
        event.remove(
            conn.sync_connection, "before_cursor_execute", substitute_extension
        )

    assert substitutions == [
        ("CREATE EXTENSION IF NOT EXISTS vector", f'CREATE EXTENSION "{missing}"')
    ]
    assert lifespan_module.runtime_flags.semantic_search_enabled is False
    assert await conn.scalar(select(func.count()).select_from(table(name))) == 0
    await _assert_outer_work(conn, transaction_id)


async def test_enabled_search_fails_closed_on_real_postgres_extension_error(
    startup_connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = startup_connection
    _install_startup_test_environment(
        monkeypatch, conn, semantic_search_enabled=True, vector_column=False
    )
    missing = await _missing_extension_name(conn)
    transaction_id = await conn.scalar(text("SELECT txid_current()"))
    assert isinstance(transaction_id, int)
    substitutions: list[tuple[str, str]] = []

    def substitute_extension(_conn, _cursor, statement, parameters, _context, _many):  # type: ignore[no-untyped-def]
        if statement == "CREATE EXTENSION IF NOT EXISTS vector":
            replacement = f'CREATE EXTENSION "{missing}"'
            substitutions.append((statement, replacement))
            return replacement, parameters
        return statement, parameters

    event.listen(
        conn.sync_connection, "before_cursor_execute", substitute_extension, retval=True
    )
    try:
        with pytest.raises(DBAPIError) as failure:
            await lifespan_module._handle_schema_and_extensions()
    finally:
        event.remove(
            conn.sync_connection, "before_cursor_execute", substitute_extension
        )
    assert substitutions == [
        ("CREATE EXTENSION IF NOT EXISTS vector", f'CREATE EXTENSION "{missing}"')
    ]
    assert getattr(failure.value.orig, "sqlstate", None) in {"0A000", "58P01"}
    await _assert_outer_work(conn, transaction_id)


async def test_disabled_search_does_not_hide_missing_vector_type_on_fresh_schema(
    startup_connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = startup_connection
    _install_startup_test_environment(
        monkeypatch, conn, semantic_search_enabled=False, vector_column=True
    )
    missing = await _missing_extension_name(conn)
    await conn.execute(text("SET LOCAL search_path TO pg_temp, pg_catalog"))
    assert await conn.scalar(text("SELECT to_regtype('vector')")) is None
    transaction_id = await conn.scalar(text("SELECT txid_current()"))
    assert isinstance(transaction_id, int)
    substitutions: list[tuple[str, str]] = []

    def substitute_extension(_conn, _cursor, statement, parameters, _context, _many):  # type: ignore[no-untyped-def]
        if statement == "CREATE EXTENSION IF NOT EXISTS vector":
            replacement = f'CREATE EXTENSION "{missing}"'
            substitutions.append((statement, replacement))
            return replacement, parameters
        return statement, parameters

    event.listen(
        conn.sync_connection, "before_cursor_execute", substitute_extension, retval=True
    )
    try:
        with pytest.raises(DBAPIError) as failure:
            await lifespan_module._handle_schema_and_extensions()
    finally:
        event.remove(
            conn.sync_connection, "before_cursor_execute", substitute_extension
        )
    assert substitutions == [
        ("CREATE EXTENSION IF NOT EXISTS vector", f'CREATE EXTENSION "{missing}"')
    ]
    assert getattr(failure.value.orig, "sqlstate", None) == "42704"
    await _assert_outer_work(conn, transaction_id)


async def test_existing_pgvector_remains_enabled_and_builds_vector_column(
    startup_connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = startup_connection
    assert await conn.scalar(
        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    )
    assert await conn.scalar(text("SELECT to_regtype('vector')")) is not None
    name = _install_startup_test_environment(
        monkeypatch, conn, semantic_search_enabled=True, vector_column=True
    )
    transaction_id = await conn.scalar(text("SELECT txid_current()"))
    assert isinstance(transaction_id, int)

    await lifespan_module._handle_schema_and_extensions()

    assert lifespan_module.settings.semantic_search_enabled is True
    assert await conn.scalar(select(func.count()).select_from(table(name))) == 0
    await _assert_outer_work(conn, transaction_id)
