"""PostgreSQL catalog regressions for literal-scalar default preflight."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core import database
from tests.test_be02_literal_scalar_defaults_migration import _load_migration

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest.mark.parametrize("operation", ["upgrade", "downgrade"])
@pytest.mark.parametrize("literal", ["'pending'", "'PENDING'", "'pen ding'"])
async def test_postgresql_literal_preflight_and_contract_preservation(
    operation: str, literal: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use actual pg_get_expr output, rolling back the isolated schema afterwards."""

    assert database.engine.dialect.name == "postgresql", (
        "RUN_INTEGRATION_TESTS requires the isolated PostgreSQL test harness"
    )
    migration = _load_migration()
    specs = (
        migration.DefaultSpec("defaults_probe", "count", "0", "integer"),
        migration.DefaultSpec("defaults_probe", "ratio", "0.0", "float"),
        migration.DefaultSpec("defaults_probe", "enabled", "true", "boolean"),
        migration.DefaultSpec("defaults_probe", "status", "'pending'", "text"),
    )
    monkeypatch.setattr(migration, "DEFAULT_SPECS", specs)
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    def exercise(connection: sa.Connection) -> None:
        schema = f"be02_literals_{uuid4().hex}"
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        table = sa.Table(
            "defaults_probe",
            sa.MetaData(),
            sa.Column("count", sa.Integer()),
            sa.Column("ratio", sa.Float()),
            sa.Column("enabled", sa.Boolean()),
            sa.Column("status", sa.String(20), server_default=sa.text(literal)),
        )
        table.create(connection)
        connection.execute(table.insert().values(count=None, status=None))
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        before = [migration._catalog_state(connection, spec) for spec in specs]
        if literal != "'pending'":
            with pytest.raises(RuntimeError, match="conflicting server default"):
                getattr(migration, operation)()
            assert [
                migration._catalog_state(connection, spec) for spec in specs
            ] == before
            assert connection.execute(sa.select(table)).one() == (
                None,
                None,
                None,
                None,
            )
            assert migration._constraint_rows(connection, specs[0]) == []
            return

        # Establish the additive contract, then verify both idempotent upgrade
        # and contract-preserving downgrade against the actual catalog.
        migration.upgrade()
        upgraded = [migration._catalog_state(connection, spec) for spec in specs]
        assert all(
            state.not_null and state.default_sql is not None for state in upgraded
        )
        assert upgraded[-1].default_sql == before[-1].default_sql
        assert connection.execute(sa.select(table)).one() == (0, 0.0, True, "pending")
        getattr(migration, operation)()
        assert [
            migration._catalog_state(connection, spec) for spec in specs
        ] == upgraded
        inserted = connection.execute(table.insert().returning(table)).one()
        assert inserted == (0, 0.0, True, "pending")

    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()
