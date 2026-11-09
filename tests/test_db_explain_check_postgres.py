"""Owned PostgreSQL integration checks for the DB EXPLAIN gate."""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import (
    Column,
    Index,
    MetaData,
    Table,
    Text,
    bindparam,
    literal_column,
    select,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import db_explain_check

pytestmark = pytest.mark.integration


class _PinnedConnectionView:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def begin(self) -> Any:
        return self._connection.begin_nested()

    def begin_nested(self) -> Any:
        return self._connection.begin_nested()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _PinnedConnectionEngine:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_PinnedConnectionView]:
        yield _PinnedConnectionView(self._connection)


class _FailOnceWithPostgresSyntaxError:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._fail_once = True

    async def exec_driver_sql(self, statement: str, *args: Any, **kwargs: Any) -> Any:
        if self._fail_once and statement.startswith("EXPLAIN "):
            self._fail_once = False
            statement += " INVALID"
        return await self._connection.exec_driver_sql(statement, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _jsonb_operator_queries(table: Table) -> tuple[str, ...]:
    predicates = (
        table.c.json_data.has_key(bindparam("lookup_key", type_=Text())),
        table.c.json_data.has_any(bindparam("lookup_keys_any", type_=ARRAY(Text()))),
        table.c.json_data.has_all(bindparam("lookup_keys_all", type_=ARRAY(Text()))),
        table.c.json_data.contains(bindparam("lookup_document", type_=JSONB())),
    )
    dialect = postgresql.dialect(paramstyle="qmark")
    return tuple(
        str(select(table).where(predicate).compile(dialect=dialect))
        for predicate in predicates
    )


@pytest.fixture(scope="module", autouse=True)
def prepare_database() -> Iterator[None]:
    """Use only the explicit owned server; skip shared app DB setup."""
    yield


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    """The tests own only rollback-scoped temporary PostgreSQL objects."""
    yield


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run",
)
async def test_live_postgres_error_after_prepare_allows_same_session_retry() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    query = "SELECT * FROM pg_catalog.pg_class WHERE oid = $1"
    statement_name = db_explain_check._plan_statement_name(query)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                failing_connection = _FailOnceWithPostgresSyntaxError(connection)
                with pytest.raises(DBAPIError, match="syntax error"):
                    await db_explain_check.explain_plan(failing_connection, query)

                plan = await db_explain_check.explain_plan(failing_connection, query)
                assert db_explain_check._extract_usable_explain_plan(plan) is not None

                prepared = await connection.execute(
                    text(
                        "SELECT name FROM pg_prepared_statements "
                        "WHERE name = :statement_name"
                    ),
                    {"statement_name": statement_name},
                )
                assert prepared.scalar() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run",
)
async def test_strict_gate_sees_all_bind_forms_on_live_postgres() -> None:
    """AUD-461: generic plans expose Seq Scans for every supported bind form."""

    engine = create_async_engine(os.environ["DATABASE_URL"])
    suffix = uuid4().hex
    unindexed_name = f"aud461_{suffix}_unindexed"
    indexed_name = f"aud461_{suffix}_indexed"
    metadata = MetaData()
    unindexed_table = Table(
        unindexed_name,
        metadata,
        Column("id", UUID(as_uuid=True), nullable=False),
        Column("json_data", JSONB, nullable=False),
        prefixes=["TEMPORARY"],
    )
    indexed_table = Table(
        indexed_name,
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("json_data", JSONB, nullable=False),
        prefixes=["TEMPORARY"],
    )
    Index(
        f"{indexed_name}_json_gin",
        indexed_table.c.json_data,
        postgresql_using="gin",
    )
    parameter_styles = ("numeric_dollar", "named", "qmark")
    unindexed_results = []
    indexed_results = []
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.run_sync(metadata.create_all)
                pinned_engine = _PinnedConnectionEngine(connection)

                for parameter_style in parameter_styles:
                    query = str(
                        select(unindexed_table)
                        .where(unindexed_table.c.id == bindparam("lookup_id"))
                        .compile(dialect=postgresql.dialect(paramstyle=parameter_style))
                    )
                    unindexed_results.append(
                        await db_explain_check.run_explain_analysis(
                            pinned_engine,
                            [query],
                            [unindexed_name],
                            500.0,
                            fail_on_analysis_error=True,
                        )
                    )

                for parameter_style in parameter_styles:
                    query = str(
                        select(indexed_table)
                        .where(indexed_table.c.id == bindparam("lookup_id"))
                        .compile(dialect=postgresql.dialect(paramstyle=parameter_style))
                    )
                    indexed_results.append(
                        await db_explain_check.run_explain_analysis(
                            pinned_engine,
                            [query],
                            [indexed_name],
                            500.0,
                            fail_on_analysis_error=True,
                        )
                    )

                unindexed_json_results = []
                for query in _jsonb_operator_queries(unindexed_table):
                    unindexed_json_results.append(
                        await db_explain_check.run_explain_analysis(
                            pinned_engine,
                            [query],
                            [unindexed_name],
                            500.0,
                            fail_on_analysis_error=True,
                        )
                    )

                indexed_json_results = []
                for query in _jsonb_operator_queries(indexed_table):
                    indexed_json_results.append(
                        await db_explain_check.run_explain_analysis(
                            pinned_engine,
                            [query],
                            [indexed_name],
                            500.0,
                            fail_on_analysis_error=True,
                        )
                    )

                await connection.run_sync(metadata.drop_all)
    finally:
        await engine.dispose()

    assert unindexed_results == [(True, 1)] * len(parameter_styles)
    assert indexed_results == [(False, 1)] * len(parameter_styles)
    assert unindexed_json_results == [(True, 1)] * 4
    assert indexed_json_results == [(False, 1)] * 4


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run",
)
async def test_live_postgres_show_mode_drives_ordinary_string_lexer() -> None:
    """Verify real SHOW values select ordinary-string escape behavior."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    suffix = uuid4().hex
    indexed_name = f"aud461_{suffix}_indexed"
    metadata = MetaData()
    indexed_table = Table(
        indexed_name,
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("json_data", JSONB, nullable=False),
        prefixes=["TEMPORARY"],
    )
    Index(
        f"{indexed_name}_json_gin",
        indexed_table.c.json_data,
        postgresql_using="gin",
    )
    cases = (
        ("on", r"'C:\'"),
        ("off", r"'it\'s ?'"),
    )
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.run_sync(metadata.create_all)
                pinned_engine = _PinnedConnectionEngine(connection)

                for setting, string_literal in cases:
                    await connection.exec_driver_sql(
                        f"SET LOCAL standard_conforming_strings = {setting}"
                    )
                    observed = await connection.exec_driver_sql(
                        "SHOW standard_conforming_strings"
                    )
                    assert observed.scalar_one() == setting

                    # Keep the GUC-sensitive literal raw while SQLAlchemy composes identifiers.
                    query = str(
                        select(indexed_table)
                        .where(
                            indexed_table.c.json_data.op("->>", return_type=Text())(
                                literal_column("'note'")
                            )
                            == literal_column(string_literal, type_=Text())
                        )
                        .where(indexed_table.c.id == bindparam("lookup_id"))
                        .compile(dialect=postgresql.dialect(paramstyle="named"))
                    )
                    violations, checked = await db_explain_check.run_explain_analysis(
                        pinned_engine,
                        [query],
                        [indexed_name],
                        500.0,
                        fail_on_analysis_error=True,
                    )
                    assert violations is False
                    assert checked == 1

                await connection.run_sync(metadata.drop_all)
    finally:
        await engine.dispose()
