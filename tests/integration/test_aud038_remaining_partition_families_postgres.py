from __future__ import annotations

import importlib.util
import os
import re
import sys
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
import yaml
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event
from testcontainers.community.postgres import PostgresContainer

from tests.integration.owned_postgres import _LoopbackMigrationPostgres

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "202607020001_create_range_partitions.py"
)
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

_TABLE_DDL = {
    "data_access_logs": (
        "CREATE TABLE data_access_logs ("
        "id uuid NOT NULL, actor_user_id uuid, subject_user_id uuid, "
        "resource_type varchar(64) NOT NULL, resource_id varchar(128), "
        "action varchar(64) NOT NULL, context json, ip_address varchar(64), "
        "user_agent varchar(512), created_at timestamptz NOT NULL DEFAULT now(), "
        "signature varchar(512), "
        "CONSTRAINT data_access_logs_pkey PRIMARY KEY (id, created_at), "
        "CONSTRAINT fk_data_access_logs_actor_user_id "
        "FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL, "
        "CONSTRAINT fk_data_access_logs_subject_user_id "
        "FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE SET NULL"
        ") PARTITION BY RANGE (created_at)"
    ),
    "failed_login_attempts": (
        "CREATE TABLE failed_login_attempts ("
        "id uuid NOT NULL, user_id uuid, email varchar(254) NOT NULL, "
        "ip_address varchar(45), user_agent varchar(512), "
        "attempted_at timestamptz NOT NULL DEFAULT now(), "
        "CONSTRAINT failed_login_attempts_pkey PRIMARY KEY (id, attempted_at), "
        "CONSTRAINT fk_failed_login_attempts_user_id "
        "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL"
        ") PARTITION BY RANGE (attempted_at)"
    ),
}
_DEFAULT_PARTITION_DDL = {
    "data_access_logs": (
        "CREATE TABLE data_access_logs_default PARTITION OF data_access_logs DEFAULT"
    ),
    "failed_login_attempts": (
        "CREATE TABLE failed_login_attempts_default "
        "PARTITION OF failed_login_attempts DEFAULT"
    ),
}
_TABLE_KEYS = {
    "data_access_logs": "created_at",
    "failed_login_attempts": "attempted_at",
}
_INDEX_DDL = (
    "CREATE INDEX ix_data_access_logs_action ON data_access_logs (action)",
    "CREATE INDEX ix_data_access_logs_actor_user_id "
    "ON data_access_logs (actor_user_id)",
    "CREATE INDEX ix_data_access_logs_created_at ON data_access_logs (created_at)",
    "CREATE INDEX ix_data_access_logs_resource_id ON data_access_logs (resource_id)",
    "CREATE INDEX ix_data_access_logs_resource_type "
    "ON data_access_logs (resource_type)",
    "CREATE INDEX ix_data_access_logs_subject_user_id "
    "ON data_access_logs (subject_user_id)",
    "CREATE INDEX ix_failed_login_attempts_attempted_at "
    "ON failed_login_attempts (attempted_at)",
    "CREATE INDEX ix_failed_login_attempts_email ON failed_login_attempts (email)",
    "CREATE INDEX ix_failed_login_attempts_email_attempted_at "
    "ON failed_login_attempts (email, attempted_at)",
    "CREATE INDEX ix_failed_login_attempts_ip_address "
    "ON failed_login_attempts (ip_address)",
    "CREATE INDEX ix_failed_login_attempts_ip_attempted_at "
    "ON failed_login_attempts (ip_address, attempted_at)",
    "CREATE INDEX ix_failed_login_attempts_user_id ON failed_login_attempts (user_id)",
)


def _pinned_postgres_image() -> str:
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    )
    image = compose["services"]["postgres"]["image"]
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise ValueError("docker-compose.test.yml must pin pgvector/pg17 by SHA-256")
    return image


@pytest.fixture(scope="module")
def postgres_engine():
    """Use an owned loopback test database or the bounded pinned PG17 fallback."""
    operator_url = os.environ.get("MIGRATION_ROUNDTRIP_DATABASE_URL")
    if operator_url:
        operator = _LoopbackMigrationPostgres(operator_url)
        database_name = f"test_{uuid4().hex[:20]}"
        admin_engine = sa.create_engine(
            operator.get_maintenance_connection_url(driver="psycopg"),
            isolation_level="AUTOCOMMIT",
        )
        target_url = operator.get_test_connection_url(database_name, driver="psycopg")
        database_created = False
        engine: sa.Engine | None = None
        try:
            quoted_database = admin_engine.dialect.identifier_preparer.quote(
                database_name
            )
            with admin_engine.connect() as admin:
                collision = admin.execute(
                    sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": database_name},
                ).scalar_one_or_none()
                if collision is not None:
                    raise RuntimeError("Generated AUD038 database name already exists.")
                admin.exec_driver_sql(f"CREATE DATABASE {quoted_database}")
                database_created = True

            engine = sa.create_engine(target_url)
            yield engine
        finally:
            try:
                if engine is not None:
                    engine.dispose()
            finally:
                try:
                    if database_created:
                        with admin_engine.connect() as admin:
                            admin.exec_driver_sql(f"DROP DATABASE {quoted_database}")
                finally:
                    admin_engine.dispose()
        return

    run_id = uuid4().hex
    postgres = PostgresContainer(
        _pinned_postgres_image(),
        name=f"ue-aud038-remaining-families-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"aud038-remaining-{run_id}",
            "university-ecosystem.dev/test-purpose": "default-partition-redistribution",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
        pids_limit=256,
    )
    cast(Any, postgres.ports)[str(postgres.port)] = ("127.0.0.1", None)
    with postgres:
        engine = sa.create_engine(postgres.get_connection_url(driver="psycopg"))
        try:
            yield engine
        finally:
            engine.dispose()


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "aud038_remaining_partition_families", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _attach_migration(migration, connection: sa.Connection) -> None:
    migration.op = Operations(MigrationContext.configure(connection))


def _create_populated_schema(engine: sa.Engine, migration, *, anchor: datetime):
    owner_id = uuid4()
    periods = {
        "current": anchor + timedelta(days=10),
        "previous": migration._add_months(anchor, -1) + timedelta(days=10),
        "outside": migration._add_months(anchor, -24) + timedelta(days=10),
    }
    row_ids = {
        table_name: {period: uuid4() for period in periods} for table_name in _TABLE_DDL
    }

    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(
            sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": owner_id}
        )
        for table_name, ddl in _TABLE_DDL.items():
            connection.execute(sa.text(ddl))
            connection.execute(sa.text(_DEFAULT_PARTITION_DDL[table_name]))
        for ddl in _INDEX_DDL:
            connection.execute(sa.text(ddl))

        access_logs = sa.Table(
            "data_access_logs", sa.MetaData(), schema="public", autoload_with=connection
        )
        failed_attempts = sa.Table(
            "failed_login_attempts",
            sa.MetaData(),
            schema="public",
            autoload_with=connection,
        )
        connection.execute(
            sa.insert(access_logs),
            [
                {
                    "id": row_ids["data_access_logs"][period],
                    "actor_user_id": owner_id,
                    "subject_user_id": owner_id,
                    "resource_type": "account",
                    "resource_id": f"audit-{period}",
                    "action": "read",
                    "context": {"partitionProbe": period},
                    "ip_address": "192.0.2.10",
                    "user_agent": f"migration-fixture/{period}",
                    "created_at": created_at,
                    "signature": None,
                }
                for period, created_at in periods.items()
            ],
        )
        connection.execute(
            sa.insert(failed_attempts),
            [
                {
                    "id": row_ids["failed_login_attempts"][period],
                    "user_id": owner_id,
                    "email": f"probe-{period}@example.test",
                    "ip_address": "198.51.100.12",
                    "user_agent": f"migration-fixture/{period}",
                    "attempted_at": attempted_at,
                }
                for period, attempted_at in periods.items()
            ],
        )

    return owner_id, periods, row_ids


def _reflected_table(connection: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(
        table_name, sa.MetaData(), schema="public", autoload_with=connection
    )


def _row_snapshot(connection: sa.Connection, table_name: str) -> tuple[tuple, ...]:
    table = _reflected_table(connection, table_name)
    partition_key = _TABLE_KEYS[table_name]
    rows = connection.execute(
        sa.select(table).order_by(table.c.id, table.c[partition_key])
    ).mappings()
    return tuple(tuple(row[column.name] for column in table.columns) for row in rows)


def _catalog_snapshot(connection: sa.Connection, table_name: str) -> dict[str, tuple]:
    inspector = sa.inspect(connection)
    columns = tuple(
        (
            column["name"],
            column["type"].compile(dialect=connection.dialect),
            bool(column["nullable"]),
            column.get("default"),
        )
        for column in inspector.get_columns(table_name, schema="public")
    )
    primary_key = inspector.get_pk_constraint(table_name, schema="public")
    primary_key_identity = (
        primary_key.get("name"),
        tuple(primary_key.get("constrained_columns") or ()),
    )
    foreign_keys = tuple(
        sorted(
            (
                foreign_key.get("name"),
                tuple(foreign_key.get("constrained_columns") or ()),
                foreign_key.get("referred_schema"),
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                str((foreign_key.get("options") or {}).get("ondelete") or "").upper(),
            )
            for foreign_key in inspector.get_foreign_keys(table_name, schema="public")
        )
    )
    indexes = tuple(
        sorted(
            (
                index.get("name"),
                tuple(index.get("column_names") or ()),
                bool(index.get("unique", False)),
            )
            for index in inspector.get_indexes(table_name, schema="public")
            if not index.get("duplicates_constraint")
        )
    )
    return {
        "columns": columns,
        "primary_key": primary_key_identity,
        "foreign_keys": foreign_keys,
        "indexes": indexes,
    }


def _default_partition_catalog_snapshot(
    connection: sa.Connection, table_name: str
) -> dict[str, object]:
    relation = f"public.{table_name}_default"
    relation_oid = connection.execute(
        sa.text("SELECT to_regclass(:relation)::oid"), {"relation": relation}
    ).scalar_one()
    indexes = connection.execute(
        sa.text(
            "SELECT index_relation.oid, index_relation.relname, "
            "pg_get_indexdef(index_relation.oid) "
            "FROM pg_index AS index_metadata "
            "JOIN pg_class AS index_relation "
            "ON index_relation.oid = index_metadata.indexrelid "
            "WHERE index_metadata.indrelid = to_regclass(:relation) "
            "ORDER BY index_relation.relname"
        ),
        {"relation": relation},
    ).all()
    return {
        "relation_oid": relation_oid,
        "indexes": tuple(tuple(row) for row in indexes),
    }


def _partition_children(connection: sa.Connection, table_name: str) -> set[str]:
    children = connection.execute(
        sa.text(
            "SELECT child.relname FROM pg_inherits AS inheritance "
            "JOIN pg_class AS child ON child.oid = inheritance.inhrelid "
            "WHERE inheritance.inhparent = to_regclass(:parent) "
            "AND child.relispartition"
        ),
        {"parent": f"public.{table_name}"},
    ).scalars()
    return set(children)


def _row_placements(
    connection: sa.Connection, table_name: str
) -> dict[str, tuple[str, str]]:
    table = _reflected_table(connection, table_name)
    partition_key = _TABLE_KEYS[table_name]
    rows = connection.execute(
        sa.select(
            table.c.id,
            table.c[partition_key],
            sa.literal_column("tableoid::regclass::text").label("partition_name"),
        ).order_by(table.c.id)
    ).all()
    return {
        str(row.id): (
            str(row.partition_name).rsplit(".", maxsplit=1)[-1].strip('"'),
            row._mapping[partition_key].astimezone(UTC).strftime("%Y_%m"),
        )
        for row in rows
    }


def _assert_set_null_on_delete(
    connection: sa.Connection,
    table_name: str,
    row_ids: dict[str, object],
) -> None:
    table = _reflected_table(connection, table_name)
    rows = connection.execute(sa.select(table)).mappings().all()
    assert len(rows) == 3
    if table_name == "data_access_logs":
        assert all(row["actor_user_id"] is None for row in rows)
        assert all(row["subject_user_id"] is None for row in rows)
    else:
        assert all(row["user_id"] is None for row in rows)
    assert {str(row["id"]) for row in rows} == {
        str(value) for value in row_ids.values()
    }


def test_upgrade_redistributes_remaining_default_partition_families(
    postgres_engine: sa.Engine, monkeypatch
) -> None:
    migration = _load_migration()
    anchor = datetime(2026, 10, 1, tzinfo=UTC)

    class FixedMigrationDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return (
                anchor.astimezone(tz) if tz is not None else anchor.replace(tzinfo=None)
            )

    monkeypatch.setattr(migration, "datetime", FixedMigrationDatetime)
    owner_id, periods, row_ids = _create_populated_schema(
        postgres_engine, migration, anchor=anchor
    )
    table_names = tuple(_TABLE_DDL)
    with postgres_engine.connect() as connection:
        original_catalog = {
            table_name: _catalog_snapshot(connection, table_name)
            for table_name in table_names
        }
        original_rows = {
            table_name: _row_snapshot(connection, table_name)
            for table_name in table_names
        }
        original_default_catalog = {
            table_name: _default_partition_catalog_snapshot(connection, table_name)
            for table_name in table_names
        }
        original_children = {
            table_name: _partition_children(connection, table_name)
            for table_name in table_names
        }
        original_placements = {
            table_name: _row_placements(connection, table_name)
            for table_name in table_names
        }

    for table_name in table_names:
        assert original_children[table_name] == {f"{table_name}_default"}
        assert original_placements[table_name] == {
            str(row_ids[table_name][period]): (
                f"{table_name}_default",
                periods[period].strftime("%Y_%m"),
            )
            for period in periods
        }

    # The second family is last in the migration's table list. Fail at its
    # DEFAULT reattach to prove the transaction rolls both families back.
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        _attach_migration(migration, connection)

        def fail_before_failed_login_default_reattach(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            normalized = statement.upper()
            if (
                "ATTACH PARTITION" in normalized
                and "FAILED_LOGIN_ATTEMPTS_DEFAULT" in normalized
                and "DEFAULT" in normalized
            ):
                raise RuntimeError("injected AUD-038 remaining-family failure")

        event.listen(
            connection,
            "before_cursor_execute",
            fail_before_failed_login_default_reattach,
        )
        try:
            with pytest.raises(
                RuntimeError, match="injected AUD-038 remaining-family failure"
            ):
                migration.upgrade()
        finally:
            event.remove(
                connection,
                "before_cursor_execute",
                fail_before_failed_login_default_reattach,
            )
            transaction.rollback()

    with postgres_engine.connect() as connection:
        assert {
            table_name: _catalog_snapshot(connection, table_name)
            for table_name in table_names
        } == original_catalog
        assert {
            table_name: _row_snapshot(connection, table_name)
            for table_name in table_names
        } == original_rows
        assert {
            table_name: _default_partition_catalog_snapshot(connection, table_name)
            for table_name in table_names
        } == original_default_catalog
        assert {
            table_name: _partition_children(connection, table_name)
            for table_name in table_names
        } == original_children
        assert {
            table_name: _row_placements(connection, table_name)
            for table_name in table_names
        } == original_placements

    with postgres_engine.begin() as connection:
        _attach_migration(migration, connection)
        migration.upgrade()

    with postgres_engine.connect() as connection:
        migrated_catalog = {
            table_name: _catalog_snapshot(connection, table_name)
            for table_name in table_names
        }
        migrated_default_catalog = {
            table_name: _default_partition_catalog_snapshot(connection, table_name)
            for table_name in table_names
        }
        assert migrated_catalog == original_catalog
        assert migrated_default_catalog == original_default_catalog
        assert {
            table_name: _row_snapshot(connection, table_name)
            for table_name in table_names
        } == original_rows
        for table_name in table_names:
            expected = {
                str(row_ids[table_name][period]): (
                    f"{table_name}_{periods[period].strftime('%Y_%m')}",
                    periods[period].strftime("%Y_%m"),
                )
                for period in ("current", "previous")
            }
            outside_id = str(row_ids[table_name]["outside"])
            expected[outside_id] = (
                f"{table_name}_default",
                periods["outside"].strftime("%Y_%m"),
            )
            assert _row_placements(connection, table_name) == expected
            children = _partition_children(connection, table_name)
            assert f"{table_name}_default" in children
            assert {
                f"{table_name}_{periods[period].strftime('%Y_%m')}"
                for period in ("current", "previous")
            } <= children

        before_repeat = {
            table_name: _partition_children(connection, table_name)
            for table_name in table_names
        }
        _attach_migration(migration, connection)
        migration.upgrade()
        assert {
            table_name: _partition_children(connection, table_name)
            for table_name in table_names
        } == before_repeat
        assert {
            table_name: _catalog_snapshot(connection, table_name)
            for table_name in table_names
        } == migrated_catalog
        assert {
            table_name: _default_partition_catalog_snapshot(connection, table_name)
            for table_name in table_names
        } == migrated_default_catalog
        assert {
            table_name: _row_snapshot(connection, table_name)
            for table_name in table_names
        } == original_rows

    with postgres_engine.begin() as connection:
        connection.execute(
            sa.text("DELETE FROM users WHERE id = :owner_id"),
            {"owner_id": owner_id},
        )
        for table_name in table_names:
            _assert_set_null_on_delete(connection, table_name, row_ids[table_name])
