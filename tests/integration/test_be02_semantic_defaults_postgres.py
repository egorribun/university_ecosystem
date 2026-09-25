"""Real PostgreSQL catalog tests for BE-02 phase four."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.core import database
from tests.test_be02_semantic_defaults_migration import _migration

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run",
    ),
]


async def test_phase_four_raw_insert_and_contract_preserving_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert database.engine.dialect.name == "postgresql"
    migration = _migration()
    timestamp = migration.DefaultSpec(
        "defaults_probe", "event_at", "now()", "timestamp"
    )
    role = migration.DefaultSpec(
        "defaults_probe", "role", "'student'::userrole", "role"
    )
    monkeypatch.setattr(migration, "DEFAULT_SPECS", (timestamp, role))
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    def exercise(connection: sa.Connection) -> None:
        schema = f"be02_semantic_{uuid4().hex}"
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        connection.execute(
            sa.text("CREATE TYPE userrole AS ENUM ('student', 'teacher', 'admin')")
        )
        table = sa.Table(
            "defaults_probe",
            sa.MetaData(),
            sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "role",
                postgresql.ENUM(
                    "student", "teacher", "admin", name="userrole", create_type=False
                ),
                nullable=False,
            ),
        )
        table.create(connection)
        # PostgreSQL resolves an unqualified relation to pg_temp first.
        connection.execute(
            sa.text(
                "CREATE TEMP TABLE defaults_probe (event_at text, role text) "
                "ON COMMIT DROP"
            )
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )

        assert (
            migration._catalog_state(connection, timestamp, schema).default_sql is None
        )
        assert migration._catalog_state(connection, role, schema).default_sql is None
        migration.upgrade()
        assert (
            migration._catalog_state(connection, timestamp, schema).default_sql
            == "now()"
        )
        assert (
            migration._catalog_state(connection, role, schema).default_sql
            == "'student'::userrole"
        )
        connection.execute(sa.text("DROP TABLE pg_temp.defaults_probe"))

        transaction_started = connection.execute(
            sa.text("SELECT transaction_timestamp()")
        ).scalar_one()
        connection.execute(sa.text("SELECT pg_sleep(0.05)"))
        inserted = connection.execute(table.insert().returning(table)).one()
        assert inserted.event_at == transaction_started
        assert inserted.event_at.tzinfo is not None
        assert inserted.role == "student"

        # ORM/Core-side Python default remains wall-clock, not transaction start.
        python_default = sa.Table(
            "defaults_probe",
            sa.MetaData(),
            sa.Column(
                "event_at",
                sa.DateTime(timezone=True),
                default=lambda: datetime.now(UTC),
            ),
            sa.Column(
                "role",
                postgresql.ENUM(
                    "student", "teacher", "admin", name="userrole", create_type=False
                ),
                default="student",
            ),
        )
        before = datetime.now(UTC)
        orm_inserted = connection.execute(
            python_default.insert().returning(python_default.c.event_at)
        ).scalar_one()
        after = datetime.now(UTC)
        assert before <= orm_inserted <= after
        assert orm_inserted > inserted.event_at

        migration.downgrade()
        assert (
            migration._catalog_state(connection, role, schema).default_sql
            == "'student'::userrole"
        )
        migration.upgrade()
        assert (
            migration._catalog_state(connection, timestamp, schema).default_sql
            == "now()"
        )

    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()


async def test_phase_four_conflicting_enum_default_aborts_before_timestamp_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert database.engine.dialect.name == "postgresql"
    migration = _migration()
    timestamp = migration.DefaultSpec(
        "defaults_probe", "event_at", "now()", "timestamp"
    )
    role = migration.DefaultSpec(
        "defaults_probe", "role", "'student'::userrole", "role"
    )
    monkeypatch.setattr(migration, "DEFAULT_SPECS", (timestamp, role))
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    def exercise(connection: sa.Connection) -> None:
        schema = f"be02_conflict_{uuid4().hex}"
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        connection.execute(sa.text("CREATE TYPE userrole AS ENUM ('student', 'admin')"))
        table = sa.Table(
            "defaults_probe",
            sa.MetaData(),
            sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "role",
                postgresql.ENUM("student", "admin", name="userrole", create_type=False),
                nullable=False,
                server_default=sa.text("'admin'::userrole"),
            ),
        )
        table.create(connection)
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        with pytest.raises(RuntimeError, match="conflicting server default"):
            migration.upgrade()
        assert (
            migration._catalog_state(connection, timestamp, schema).default_sql is None
        )
        assert (
            migration._catalog_state(connection, role, schema).default_sql
            == "'admin'::userrole"
        )

    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()


async def test_phase_four_rejects_historical_null_instead_of_fabricating_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert database.engine.dialect.name == "postgresql"
    migration = _migration()
    timestamp = migration.DefaultSpec(
        "defaults_probe", "event_at", "now()", "timestamp"
    )
    monkeypatch.setattr(migration, "DEFAULT_SPECS", (timestamp,))
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    def exercise(connection: sa.Connection) -> None:
        schema = f"be02_null_{uuid4().hex}"
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        table = sa.Table(
            "defaults_probe",
            sa.MetaData(),
            sa.Column("event_at", sa.DateTime(timezone=True)),
        )
        table.create(connection)
        connection.execute(table.insert().values(event_at=None))
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        state = migration._catalog_state(connection, timestamp, schema)
        assert state.null_count == 1
        with pytest.raises(RuntimeError, match="NOT NULL"):
            migration.upgrade()
        assert (
            migration._catalog_state(connection, timestamp, schema).default_sql is None
        )
        assert connection.execute(sa.select(table.c.event_at)).scalar_one() is None

    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()
