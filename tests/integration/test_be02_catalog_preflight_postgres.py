"""Read-only BE-02 catalog preflight against a real PostgreSQL catalog."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import exc

import scripts.be02_catalog_preflight as preflight
from app.core import database

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run",
    ),
]


def _probe(schema: str) -> sa.TableClause:
    return sa.table("probe", sa.column("pending"), schema=schema)


@pytest.fixture
def probe_schema():
    """An isolated schema with one converged, one pending and one drifted column."""

    assert database.engine.dialect.name == "postgresql"
    engine = sa.create_engine(
        preflight.sync_url(database.engine.url.render_as_string(hide_password=False))
    )
    schema = f"be02_preflight_{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text(
                f'CREATE TABLE "{schema}".probe ('
                "  converged timestamptz NOT NULL DEFAULT now(),"
                "  pending timestamptz NOT NULL,"
                "  drifted timestamptz NOT NULL DEFAULT '2000-01-01'::timestamptz,"
                "  nullable timestamptz"
                ")"
            )
        )
        connection.execute(sa.insert(_probe(schema)).values(pending=sa.func.now()))
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        engine.dispose()


def _migration_for(schema: str) -> object:
    migration = preflight.load_migration()
    migration.DEFAULT_SPECS = tuple(
        migration.DefaultSpec("probe", column, "now()", "timestamp")
        for column in ("converged", "pending", "drifted", "nullable")
    )
    migration._target_schema = lambda _connection: schema
    return migration


def test_reports_catalog_drift_without_writing(probe_schema) -> None:
    engine, schema = probe_schema
    migration = _migration_for(schema)

    with engine.connect() as connection, connection.begin():
        connection.execute(sa.text("SET TRANSACTION READ ONLY"))
        results = preflight.inspect_catalog(connection, migration)
        # The transaction stays read-only: any write attempt is rejected.
        with pytest.raises(exc.InternalError, match="read-only transaction"):
            connection.execute(sa.insert(_probe(schema)).values(pending=sa.func.now()))

    by_column = {result.column.rsplit(".", 1)[1]: result for result in results}
    assert by_column["converged"].status == "converged"
    assert by_column["pending"].status == "pending"
    assert by_column["drifted"].status == "blocked"
    assert "conflicting server default" in by_column["drifted"].detail
    assert by_column["nullable"].status == "blocked"
    assert "NOT NULL" in by_column["nullable"].detail


def test_run_executes_the_real_migration_checks_read_only(probe_schema) -> None:
    engine, schema = probe_schema
    migration = _migration_for(schema)

    results = preflight.run(engine.url.render_as_string(hide_password=False), migration)

    assert [result.status for result in results] == [
        "converged",
        "pending",
        "blocked",
        "blocked",
    ]
