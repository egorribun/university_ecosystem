"""Exercise pgvector startup with actual SQLAlchemy transaction boundaries."""

import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core import lifespan as lifespan_module


async def _exercise_schema_startup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sqlstate: str | None,
    semantic_search_enabled: bool,
    fail_rollback: bool = False,
    fail_schema: bool = False,
    error_attribute: str = "sqlstate",
    fail_savepoint: bool = False,
    fail_network: bool = False,
    disconnect: bool = False,
) -> tuple[list[str], AsyncEngine]:
    """Use SQLite for SQLAlchemy transactions and emulate PostgreSQL abort state.

    ``do_execute`` raises a real DBAPI exception on CREATE EXTENSION.  The
    connection remains unusable after that error until a real savepoint rollback,
    matching the relevant PostgreSQL transaction rule.  SQLite is not a substitute
    for the separate PostgreSQL integration test.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine.sync_engine.dialect.name = "postgresql"
    if disconnect:
        monkeypatch.setattr(
            engine.sync_engine.dialect, "is_disconnect", lambda *_: True
        )
    statements: list[str] = []
    transaction_aborted = False

    @event.listens_for(engine.sync_engine, "do_execute")
    def execute(cursor, statement, parameters, context):  # type: ignore[no-untyped-def]
        nonlocal transaction_aborted
        del context
        statements.append(statement)
        if fail_savepoint and statement.startswith("SAVEPOINT"):
            error = sqlite3.OperationalError("savepoint refused")
            error.sqlstate = "0A000"  # type: ignore[attr-defined]
            raise error
        if statement.startswith("ROLLBACK TO SAVEPOINT"):
            if fail_rollback:
                error = sqlite3.OperationalError("rollback refused")
                error.sqlstate = "0A000"  # type: ignore[attr-defined]
                raise error
            transaction_aborted = False
        elif transaction_aborted:
            error = sqlite3.OperationalError("current transaction is aborted")
            error.sqlstate = "25P02"  # type: ignore[attr-defined]
            raise error
        elif statement == "CREATE EXTENSION IF NOT EXISTS vector":
            if fail_network:
                transaction_aborted = True
                raise ConnectionError("connection lost")
            if sqlstate is None:
                cursor.execute("SELECT 1")
                return True
            transaction_aborted = True
            error = sqlite3.OperationalError("extension unavailable")
            setattr(error, error_attribute, sqlstate)
            raise error
        elif fail_schema and statement.lstrip().startswith("CREATE TEMPORARY TABLE"):
            error = sqlite3.OperationalError("schema creation failed")
            error.sqlstate = "XX000"  # type: ignore[attr-defined]
            raise error
        return None

    metadata = MetaData()
    Table(
        "aud389_startup_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        prefixes=["TEMPORARY"],
    )
    monkeypatch.setattr(lifespan_module, "engine", engine)
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
    return statements, engine


@pytest.mark.parametrize(
    ("sqlstate", "error_attribute"),
    [("0A000", "sqlstate"), ("58P01", "sqlstate"), ("0A000", "pgcode")],
)
async def test_missing_vector_rolls_back_savepoint_and_builds_disabled_schema(
    monkeypatch: pytest.MonkeyPatch, sqlstate: str, error_attribute: str
) -> None:
    statements, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate=sqlstate,
        semantic_search_enabled=False,
        error_attribute=error_attribute,
    )
    try:
        await lifespan_module._handle_schema_and_extensions()
        async with engine.connect() as conn:
            assert (
                await conn.scalar(text("SELECT COUNT(*) FROM aud389_startup_probe"))
                == 0
            )
        assert any(statement.startswith("SAVEPOINT") for statement in statements)
        assert any(
            statement.startswith("ROLLBACK TO SAVEPOINT") for statement in statements
        )
        assert lifespan_module.runtime_flags.semantic_search_enabled is False
    finally:
        await engine.dispose()


async def test_missing_vector_with_enabled_search_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements, engine = await _exercise_schema_startup(
        monkeypatch, sqlstate="0A000", semantic_search_enabled=True
    )
    try:
        with pytest.raises(DBAPIError) as failure:
            await lifespan_module._handle_schema_and_extensions()
        assert getattr(failure.value.orig, "sqlstate", None) == "0A000"
        assert not any(
            "CREATE TEMPORARY TABLE" in statement for statement in statements
        )
        assert lifespan_module.runtime_flags.semantic_search_enabled is None
    finally:
        await engine.dispose()


async def test_failed_savepoint_rollback_is_not_treated_as_missing_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate="0A000",
        semantic_search_enabled=False,
        fail_rollback=True,
    )
    try:
        with pytest.raises(DBAPIError, match="rollback refused"):
            await lifespan_module._handle_schema_and_extensions()
        assert not any(
            "CREATE TEMPORARY TABLE" in statement for statement in statements
        )
    finally:
        await engine.dispose()


async def test_connection_error_is_not_treated_as_missing_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate=None,
        semantic_search_enabled=False,
        fail_network=True,
    )
    try:
        with pytest.raises(ConnectionError, match="connection lost"):
            await lifespan_module._handle_schema_and_extensions()
        assert lifespan_module.runtime_flags.semantic_search_enabled is None
    finally:
        await engine.dispose()


async def test_invalidated_connection_is_not_treated_as_missing_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate="0A000",
        semantic_search_enabled=False,
        disconnect=True,
    )
    try:
        with pytest.raises(DBAPIError) as failure:
            await lifespan_module._handle_schema_and_extensions()
        assert failure.value.connection_invalidated is True
        assert lifespan_module.runtime_flags.semantic_search_enabled is None
    finally:
        await engine.dispose()


async def test_savepoint_creation_failure_is_not_treated_as_missing_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate="0A000",
        semantic_search_enabled=False,
        fail_savepoint=True,
    )
    try:
        with pytest.raises(DBAPIError, match="savepoint refused"):
            await lifespan_module._handle_schema_and_extensions()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("sqlstate", [None, "0A000"])
async def test_schema_creation_failure_is_not_a_pgvector_fallback(
    monkeypatch: pytest.MonkeyPatch, sqlstate: str | None
) -> None:
    _, engine = await _exercise_schema_startup(
        monkeypatch,
        sqlstate=sqlstate,
        semantic_search_enabled=False,
        fail_schema=True,
    )
    try:
        with pytest.raises(DBAPIError, match="schema creation failed"):
            await lifespan_module._handle_schema_and_extensions()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("sqlstate", ["42501", "XX000"])
async def test_unexpected_database_errors_do_not_become_missing_vector_fallback(
    monkeypatch: pytest.MonkeyPatch, sqlstate: str
) -> None:
    statements, engine = await _exercise_schema_startup(
        monkeypatch, sqlstate=sqlstate, semantic_search_enabled=False
    )
    try:
        with pytest.raises(DBAPIError) as failure:
            await lifespan_module._handle_schema_and_extensions()
        assert getattr(failure.value.orig, "sqlstate", None) == sqlstate
        assert not any(
            "CREATE TEMPORARY TABLE" in statement for statement in statements
        )
    finally:
        await engine.dispose()


@pytest.mark.parametrize("semantic_search_enabled", [True, False])
async def test_available_vector_keeps_configured_search_setting(
    monkeypatch: pytest.MonkeyPatch, semantic_search_enabled: bool
) -> None:
    statements, engine = await _exercise_schema_startup(
        monkeypatch, sqlstate=None, semantic_search_enabled=semantic_search_enabled
    )
    try:
        await lifespan_module._handle_schema_and_extensions()
        assert (
            lifespan_module.settings.semantic_search_enabled is semantic_search_enabled
        )
        assert lifespan_module.runtime_flags.semantic_search_enabled is None
        async with engine.connect() as conn:
            assert (
                await conn.scalar(text("SELECT COUNT(*) FROM aud389_startup_probe"))
                == 0
            )
        assert not any(
            statement.startswith("ROLLBACK TO SAVEPOINT") for statement in statements
        )
    finally:
        await engine.dispose()
