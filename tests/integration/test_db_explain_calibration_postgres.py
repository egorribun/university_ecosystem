"""AUD-504: planner calibration is observable only in rollback-only analysis."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    event,
    literal_column,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from scripts import db_explain_check

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for the PostgreSQL regression",
    ),
]


async def _catalog_stats(
    connection: AsyncConnection, table: str
) -> dict[str, tuple[int, float, int]]:
    rows = await connection.execute(
        text(
            "SELECT relname, relpages, reltuples, relallvisible "
            "FROM pg_class WHERE oid = to_regclass(:table) "
            "OR oid IN (SELECT indexrelid FROM pg_index "
            "WHERE indrelid = to_regclass(:table))"
        ),
        {"table": table},
    )
    return {row[0]: tuple(row[1:]) for row in rows}


@pytest_asyncio.fixture
async def gate_probe():
    engine = create_async_engine(
        os.environ["DATABASE_URL"], pool_size=2, max_overflow=0
    )
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"
    table = f"aud504_probe_{uuid4().hex}"
    probe = Table(table, MetaData(), Column("id", Integer, primary_key=True))
    try:
        async with engine.connect() as observer:
            async with observer.begin():
                await observer.run_sync(probe.create)
                await observer.exec_driver_sql(
                    f"ALTER TABLE {table} SET (autovacuum_enabled = false)"
                )
                await observer.execute(probe.insert().values(id=1))
                await observer.exec_driver_sql(f"ANALYZE {table}")
            try:
                before = await _catalog_stats(observer, table)
                await observer.rollback()
                yield engine, observer, probe, before
            finally:
                await observer.rollback()
                async with observer.begin():
                    await observer.exec_driver_sql(f"DROP TABLE {table}")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "strict", "expected_violations", "expected_checked"),
    [
        ("success", True, False, 1),
        ("explain-error", True, True, 2),
        ("explain-error", False, False, 2),
        ("no-target", True, False, 0),
    ],
)
async def test_calibration_is_private_to_analysis_and_never_persisted(
    gate_probe,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    strict: bool,
    expected_violations: bool,
    expected_checked: int,
) -> None:
    engine, observer, probe, before = gate_probe
    table = probe.name
    observations = []
    planned = []
    original_explain = db_explain_check.explain_plan

    async def observe_explain(
        connection,
        query,
        *,
        standard_conforming_strings: bool | None = None,
    ):
        observations.append(
            (
                await _catalog_stats(connection, table),
                await _catalog_stats(observer, table),
            )
        )
        plan = await original_explain(
            connection,
            query,
            standard_conforming_strings=standard_conforming_strings,
        )
        planned.append(query)
        return plan

    monkeypatch.setattr(db_explain_check, "explain_plan", observe_explain)
    valid_query = str(select(probe).where(probe.c.id == literal_column("$1")))
    if scenario == "no-target":
        queries = ["SELECT 1"]
    elif scenario == "explain-error":
        # A real PostgreSQL error aborts the query transaction. The next query
        # must still receive calibrated statistics and produce a usable plan.
        queries = [
            str(
                select(literal_column("absent_column"))
                .select_from(probe)
                .where(probe.c.id == literal_column("1"))
            ),
            valid_query,
        ]
    else:
        queries = [valid_query]

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        queries,
        [table],
        500.0,
        fail_on_analysis_error=strict,
    )

    after = await _catalog_stats(observer, table)
    assert violations is expected_violations
    assert checked == expected_checked
    assert len(observations) == expected_checked
    assert planned == ([] if scenario == "no-target" else [valid_query])
    for visible_to_explain, visible_to_observer in observations:
        # Both table and index calibration must reach the actual planner, but
        # an independent transaction must never see these synthetic values.
        assert visible_to_explain[table] == (1000, 100000.0, 1000)
        assert visible_to_explain[f"{table}_pkey"] == (
            100,
            100000.0,
            before[f"{table}_pkey"][2],
        )
        assert visible_to_observer == before
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strict", "expected_violations"),
    [(True, True), (False, False)],
    ids=["strict-failure", "optional-warning"],
)
async def test_partial_calibration_error_restores_defaults_and_still_plans(
    gate_probe,
    monkeypatch: pytest.MonkeyPatch,
    strict: bool,
    expected_violations: bool,
) -> None:
    engine, observer, probe, before = gate_probe
    table = probe.name
    observations = []
    planned = []
    calibration_failures = []
    original_explain = db_explain_check.explain_plan

    def fail_index_calibration(
        connection, cursor, statement, parameters, context, executemany
    ):
        if statement.startswith("UPDATE pg_class") and "pg_index" in statement:
            calibration_failures.append(statement)
            # Keep the first table UPDATE real. Fail the second UPDATE inside
            # PostgreSQL, so a missing savepoint rollback leaves an aborted
            # transaction rather than merely raising a Python exception.
            return "SELECT 1 / 0 WHERE CAST($1 AS text[]) IS NOT NULL", parameters
        return statement, parameters

    async def observe_explain(
        connection,
        query,
        *,
        standard_conforming_strings: bool | None = None,
    ):
        observations.append(
            (
                await _catalog_stats(connection, table),
                await _catalog_stats(observer, table),
            )
        )
        plan = await original_explain(
            connection,
            query,
            standard_conforming_strings=standard_conforming_strings,
        )
        planned.append(query)
        return plan

    monkeypatch.setattr(db_explain_check, "explain_plan", observe_explain)
    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        fail_index_calibration,
        retval=True,
    )
    query = str(select(probe).where(probe.c.id == literal_column("$1")))
    try:
        violations, checked = await db_explain_check.run_explain_analysis(
            engine,
            [query],
            [table],
            500.0,
            fail_on_analysis_error=strict,
        )
    finally:
        event.remove(
            engine.sync_engine, "before_cursor_execute", fail_index_calibration
        )

    assert violations is expected_violations
    assert checked == 1
    assert len(calibration_failures) == 1
    assert planned == [query]
    assert observations == [(before, before)]
    assert await _catalog_stats(observer, table) == before
