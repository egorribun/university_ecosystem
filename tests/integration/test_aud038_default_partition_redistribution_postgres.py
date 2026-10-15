"""Regression for moving populated DEFAULT rows before monthly partitions attach."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from testcontainers.community.postgres import PostgresContainer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "202607020001_create_range_partitions.py"
)
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "aud038_range_partition_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def postgres_engine():
    """Use the same digest-pinned PostgreSQL 17 image as migration integration tests."""
    run_id = uuid4().hex
    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d",
        name=f"ue-aud038-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"aud038-{run_id}",
            "university-ecosystem.dev/test-purpose": "default-partition-redistribution",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
    ) as postgres:
        engine = sa.create_engine(postgres.get_connection_url(driver="psycopg"))
        try:
            yield engine
        finally:
            engine.dispose()


def _create_populated_default_schema(
    engine: sa.Engine, migration, *, anchor: datetime
) -> None:
    current_month = anchor + timedelta(days=10)
    previous_month = migration._add_months(anchor, -1) + timedelta(days=10)
    outside_window = migration._add_months(anchor, -24) + timedelta(days=10)

    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id bigint PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(
            sa.text(
                "CREATE TABLE notifications ("
                "id bigint NOT NULL, created_at timestamptz NOT NULL, "
                "user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "title text NOT NULL, "
                "CONSTRAINT notifications_pkey PRIMARY KEY (id, created_at)"
                ") PARTITION BY RANGE (created_at)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE notifications_default PARTITION OF notifications DEFAULT"
            )
        )
        connection.execute(
            sa.text("CREATE INDEX ix_notifications_user_id ON notifications (user_id)")
        )
        connection.execute(
            sa.text(
                "CREATE TABLE notification_audit ("
                "id bigint PRIMARY KEY, notification_id bigint NOT NULL, "
                "notification_created_at timestamptz NOT NULL, "
                "CONSTRAINT notification_audit_notification_fk "
                "FOREIGN KEY (notification_id, notification_created_at) "
                "REFERENCES notifications (id, created_at) ON DELETE CASCADE"
                ")"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE notification_deliveries ("
                "id bigint NOT NULL, attempted_at timestamptz NOT NULL, "
                "notification_id bigint NOT NULL, "
                "notification_created_at timestamptz NOT NULL, "
                "channel text NOT NULL, "
                "CONSTRAINT notification_deliveries_pkey "
                "PRIMARY KEY (id, attempted_at), "
                "CONSTRAINT notification_deliveries_notification_fk "
                "FOREIGN KEY (notification_id, notification_created_at) "
                "REFERENCES notifications (id, created_at) ON DELETE CASCADE"
                ") PARTITION BY RANGE (attempted_at)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE notification_deliveries_default "
                "PARTITION OF notification_deliveries DEFAULT"
            )
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_notification_deliveries_notification_id "
                "ON notification_deliveries (notification_id)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO notifications_default (id, created_at, user_id, title) "
                "VALUES (:id, :created_at, 1, :title)"
            ),
            [
                {"id": 101, "created_at": current_month, "title": "current"},
                {"id": 102, "created_at": previous_month, "title": "previous"},
                {"id": 103, "created_at": outside_window, "title": "historic"},
            ],
        )
        connection.execute(
            sa.text(
                "INSERT INTO notification_audit "
                "(id, notification_id, notification_created_at) "
                "VALUES (:id, :notification_id, :created_at)"
            ),
            [
                {"id": 301, "notification_id": 101, "created_at": current_month},
                {"id": 302, "notification_id": 102, "created_at": previous_month},
                {"id": 303, "notification_id": 103, "created_at": outside_window},
            ],
        )
        connection.execute(
            sa.text(
                "INSERT INTO notification_deliveries_default "
                "(id, attempted_at, notification_id, notification_created_at, channel) "
                "VALUES (:id, :attempted_at, :notification_id, "
                ":notification_created_at, 'email')"
            ),
            [
                {
                    "id": 201,
                    "attempted_at": current_month,
                    "notification_id": 101,
                    "notification_created_at": current_month,
                },
                {
                    "id": 202,
                    "attempted_at": previous_month,
                    "notification_id": 102,
                    "notification_created_at": previous_month,
                },
                {
                    "id": 203,
                    "attempted_at": outside_window,
                    "notification_id": 103,
                    "notification_created_at": outside_window,
                },
            ],
        )


def _ensure_historical_default_partition(
    connection: sa.Connection, parent: str, partition_key: str
) -> None:
    """Restore only the migration's expected DEFAULT child in this owned fixture DB."""
    expected_partition_keys = {
        "notifications": "created_at",
        "notification_deliveries": "attempted_at",
    }
    if expected_partition_keys.get(parent) != partition_key:
        raise AssertionError("Unexpected partition fixture parent or key")

    parent_info = connection.execute(
        sa.text(
            "SELECT relation.relkind AS relkind, "
            "pg_get_partkeydef(relation.oid) AS partition_key "
            "FROM pg_class AS relation "
            "WHERE relation.oid = to_regclass(:relation)"
        ),
        {"relation": f"public.{parent}"},
    ).one_or_none()
    assert parent_info is not None
    assert parent_info.relkind == "p"
    assert parent_info.partition_key == f"RANGE ({partition_key})"

    children = connection.execute(
        sa.text(
            "SELECT child.relname AS child_name, "
            "pg_get_expr(child.relpartbound, child.oid) AS partition_bound "
            "FROM pg_inherits AS inheritance "
            "JOIN pg_class AS parent_relation "
            "ON parent_relation.oid = inheritance.inhparent "
            "JOIN pg_class AS child "
            "ON child.oid = inheritance.inhrelid "
            "WHERE parent_relation.oid = to_regclass(:parent) "
            "AND child.relispartition "
            "ORDER BY child.relname"
        ),
        {"parent": f"public.{parent}"},
    ).all()
    default_children = [
        child for child in children if child.partition_bound == "DEFAULT"
    ]
    default_name = f"{parent}_default"
    if default_children:
        assert len(default_children) == 1
        assert default_children[0].child_name == default_name
        return

    assert default_name not in {child.child_name for child in children}
    relation_collision = connection.execute(
        sa.text("SELECT to_regclass(:relation)"),
        {"relation": f"public.{default_name}"},
    ).scalar_one()
    assert relation_collision is None

    connection.exec_driver_sql(
        f'CREATE TABLE "public"."{default_name}" '
        f'PARTITION OF "public"."{parent}" DEFAULT'
    )
    assert default_name in _partition_children(connection, parent)


def _attach_migration(migration, connection) -> None:
    migration.op = Operations(MigrationContext.configure(connection))


def _partition_children(connection, parent: str) -> set[str]:
    rows = connection.execute(
        sa.text(
            "SELECT child.relname FROM pg_inherits "
            "JOIN pg_class child ON child.oid = pg_inherits.inhrelid "
            "JOIN pg_class parent ON parent.oid = pg_inherits.inhparent "
            "JOIN pg_namespace namespace ON namespace.oid = parent.relnamespace "
            "WHERE parent.relname = :parent AND namespace.nspname = 'public' "
            "AND child.relispartition"
        ),
        {"parent": parent},
    ).scalars()
    return set(rows)


def _relation_index_identity(connection, relation_name: str) -> dict[str, object]:
    relation = f"public.{relation_name}"
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


def _parent_catalog_identity(connection, parent: str) -> dict[str, object]:
    relation = f"public.{parent}"
    constraints = connection.execute(
        sa.text(
            "SELECT oid, conname, contype, convalidated, condeferrable, "
            "condeferred, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE conrelid = to_regclass(:relation) "
            "ORDER BY conname"
        ),
        {"relation": relation},
    ).all()
    return {
        **_relation_index_identity(connection, parent),
        "constraints": tuple(tuple(row) for row in constraints),
    }


def _parent_semantic_identity(connection, parent: str) -> dict[str, object]:
    """Compare top-level definitions while allowing internal clones and new OIDs."""
    identity = _relation_index_identity(connection, parent)
    constraints = connection.execute(
        sa.text(
            "SELECT conname, contype, convalidated, condeferrable, condeferred, "
            "pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE conrelid = to_regclass(:relation) "
            "AND conparentid = 0::oid ORDER BY conname"
        ),
        {"relation": f"public.{parent}"},
    ).all()
    return {
        "relation_oid": identity["relation_oid"],
        "indexes": identity["indexes"],
        "constraints": tuple(tuple(row) for row in constraints),
    }


def _linked_audit_count(connection) -> int:
    return int(
        connection.execute(
            sa.text(
                "SELECT count(*) FROM notification_audit AS audit "
                "JOIN notifications AS notification "
                "ON notification.id = audit.notification_id "
                "AND notification.created_at = audit.notification_created_at"
            )
        ).scalar_one()
    )


def _linked_delivery_count(connection) -> int:
    return int(
        connection.execute(
            sa.text(
                "SELECT count(*) FROM notification_deliveries AS delivery "
                "JOIN notifications AS notification "
                "ON notification.id = delivery.notification_id "
                "AND notification.created_at = delivery.notification_created_at"
            )
        ).scalar_one()
    )


def _rows_by_partition(connection, parent: str) -> dict[int, str]:
    table = sa.table(parent, sa.column("id"), schema="public")
    rows = connection.execute(
        sa.select(
            table.c.id,
            sa.literal_column("tableoid::regclass::text").label("partition"),
        ).order_by(table.c.id)
    ).mappings()
    return {int(row["id"]): row["partition"] for row in rows}


def _assert_constraints_and_indexes(connection) -> None:
    expected_constraints = {
        "notifications": (
            (
                "notifications_pkey",
                "p",
                True,
                0,
                "PRIMARY KEY (id, created_at)",
            ),
            (
                "notifications_user_id_fkey",
                "f",
                True,
                0,
                "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
            ),
        ),
        "notification_deliveries": (
            (
                "notification_deliveries_notification_fk",
                "f",
                True,
                0,
                "FOREIGN KEY (notification_id, notification_created_at) "
                "REFERENCES notifications(id, created_at) ON DELETE CASCADE",
            ),
            (
                "notification_deliveries_pkey",
                "p",
                True,
                0,
                "PRIMARY KEY (id, attempted_at)",
            ),
        ),
        "notification_audit": (
            (
                "notification_audit_notification_fk",
                "f",
                True,
                0,
                "FOREIGN KEY (notification_id, notification_created_at) "
                "REFERENCES notifications(id, created_at) ON DELETE CASCADE",
            ),
            ("notification_audit_pkey", "p", True, 0, "PRIMARY KEY (id)"),
        ),
    }
    for relation, expected in expected_constraints.items():
        constraints = connection.execute(
            sa.text(
                "SELECT conname, contype, convalidated, conparentid, "
                "pg_get_constraintdef(oid, false) "
                "FROM pg_constraint WHERE conrelid = to_regclass(:relation) "
                "AND contype IN ('p', 'f') AND conparentid = 0::oid "
                "ORDER BY conname"
            ),
            {"relation": f"public.{relation}"},
        ).all()
        assert tuple(tuple(row) for row in constraints) == expected

    incoming_foreign_keys = connection.execute(
        sa.text(
            "SELECT constraint_row.conname, owner_namespace.nspname, "
            "owner_relation.relname, constraint_row.contype, "
            "constraint_row.convalidated, constraint_row.conparentid, "
            "referenced_namespace.nspname, referenced_relation.relname, "
            "pg_get_constraintdef(constraint_row.oid, false) "
            "FROM pg_constraint AS constraint_row "
            "JOIN pg_class AS owner_relation "
            "ON owner_relation.oid = constraint_row.conrelid "
            "JOIN pg_namespace AS owner_namespace "
            "ON owner_namespace.oid = owner_relation.relnamespace "
            "JOIN pg_class AS referenced_relation "
            "ON referenced_relation.oid = constraint_row.confrelid "
            "JOIN pg_namespace AS referenced_namespace "
            "ON referenced_namespace.oid = referenced_relation.relnamespace "
            "WHERE constraint_row.contype = 'f' "
            "AND constraint_row.conparentid = 0::oid "
            "AND constraint_row.confrelid = to_regclass('public.notifications') "
            "ORDER BY owner_namespace.nspname, owner_relation.relname, "
            "constraint_row.conname"
        )
    ).all()
    expected_incoming_foreign_keys = (
        (
            "notification_audit_notification_fk",
            "public",
            "notification_audit",
            "f",
            True,
            0,
            "public",
            "notifications",
            "FOREIGN KEY (notification_id, notification_created_at) "
            "REFERENCES notifications(id, created_at) ON DELETE CASCADE",
        ),
        (
            "notification_deliveries_notification_fk",
            "public",
            "notification_deliveries",
            "f",
            True,
            0,
            "public",
            "notifications",
            "FOREIGN KEY (notification_id, notification_created_at) "
            "REFERENCES notifications(id, created_at) ON DELETE CASCADE",
        ),
    )
    assert tuple(tuple(row) for row in incoming_foreign_keys) == (
        expected_incoming_foreign_keys
    )

    indexed_columns = {
        "notifications": "user_id",
        "notification_deliveries": "notification_id",
    }
    for parent, indexed_column in indexed_columns.items():
        for child in _partition_children(connection, parent):
            child_fk_count = connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conrelid = to_regclass(:relation) AND contype = 'f' "
                    "AND convalidated"
                ),
                {"relation": f"public.{child}"},
            ).scalar_one()
            assert child_fk_count >= 1
            child_index = connection.execute(
                sa.text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                    "AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = to_regclass(:relation) "
                    "AND a.attname = :column AND i.indisvalid)"
                ),
                {"relation": f"public.{child}", "column": indexed_column},
            ).scalar_one()
            assert child_index


def test_upgrade_redistributes_default_rows_atomically_and_idempotently(
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
    _create_populated_default_schema(postgres_engine, migration, anchor=anchor)
    parents = ("notifications", "notification_deliveries")
    defaults = ("notifications_default", "notification_deliveries_default")
    catalog_tables = (*parents, "notification_audit")
    with postgres_engine.connect() as connection:
        original_catalog_identity = {
            table: _parent_catalog_identity(connection, table)
            for table in catalog_tables
        }
        original_semantic_identity = {
            table: _parent_semantic_identity(connection, table)
            for table in catalog_tables
        }
        original_default_identity = {
            table: _relation_index_identity(connection, table) for table in defaults
        }

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        _attach_migration(migration, connection)

        def fail_before_default_reattach(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            normalized = statement.upper()
            if (
                "ATTACH PARTITION" in normalized
                and "NOTIFICATIONS_DEFAULT" in normalized
                and "DEFAULT" in normalized
            ):
                raise RuntimeError("injected migration transaction failure")

        event.listen(connection, "before_cursor_execute", fail_before_default_reattach)
        try:
            with pytest.raises(
                RuntimeError, match="injected migration transaction failure"
            ):
                migration.upgrade()
        finally:
            event.remove(
                connection, "before_cursor_execute", fail_before_default_reattach
            )
            transaction.rollback()

    # The failure was injected after the detach, range DDL and row transfer.
    # Transaction rollback must restore the original children and every row.
    with postgres_engine.connect() as connection:
        assert {
            table: _parent_catalog_identity(connection, table)
            for table in catalog_tables
        } == original_catalog_identity
        assert {
            table: _relation_index_identity(connection, table) for table in defaults
        } == original_default_identity
        assert _partition_children(connection, "notifications") == {
            "notifications_default"
        }
        assert _partition_children(connection, "notification_deliveries") == {
            "notification_deliveries_default"
        }
        assert _rows_by_partition(connection, "notifications") == {
            101: "notifications_default",
            102: "notifications_default",
            103: "notifications_default",
        }
        assert _rows_by_partition(connection, "notification_deliveries") == {
            201: "notification_deliveries_default",
            202: "notification_deliveries_default",
            203: "notification_deliveries_default",
        }
        assert _linked_delivery_count(connection) == 3
        assert _linked_audit_count(connection) == 3
        _assert_constraints_and_indexes(connection)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                invalid_timestamp = anchor + timedelta(days=16)
                connection.execute(
                    sa.text(
                        "INSERT INTO notification_deliveries "
                        "(id, attempted_at, notification_id, "
                        "notification_created_at, channel) "
                        "VALUES (999, :attempted_at, 999, :created_at, 'email')"
                    ),
                    {
                        "attempted_at": invalid_timestamp,
                        "created_at": invalid_timestamp,
                    },
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO notification_audit "
                        "(id, notification_id, notification_created_at) "
                        "VALUES (999, 999, :created_at)"
                    ),
                    {"created_at": invalid_timestamp},
                )

    with postgres_engine.begin() as connection:
        _attach_migration(migration, connection)
        migration.upgrade()

    with postgres_engine.begin() as connection:
        post_migration_catalog_identity = {
            table: _parent_catalog_identity(connection, table)
            for table in catalog_tables
        }
        post_migration_semantic_identity = {
            table: _parent_semantic_identity(connection, table)
            for table in catalog_tables
        }
        assert post_migration_semantic_identity == original_semantic_identity
        for table in catalog_tables:
            original_primary_key = tuple(
                constraint
                for constraint in original_catalog_identity[table]["constraints"]
                if constraint[2] == "p"
            )
            post_migration_primary_key = tuple(
                constraint
                for constraint in post_migration_catalog_identity[table]["constraints"]
                if constraint[2] == "p"
            )
            assert post_migration_primary_key == original_primary_key

        before_repeat = {
            table: _partition_children(connection, table)
            for table in ("notifications", "notification_deliveries")
        }
        _attach_migration(migration, connection)
        migration.upgrade()
        after_repeat = {
            table: _partition_children(connection, table)
            for table in ("notifications", "notification_deliveries")
        }
        assert after_repeat == before_repeat
        assert {
            table: _parent_catalog_identity(connection, table)
            for table in catalog_tables
        } == post_migration_catalog_identity
        assert {
            table: _relation_index_identity(connection, table) for table in defaults
        } == original_default_identity

        notification_months = {
            int(row.id): row.month
            for row in connection.execute(
                sa.text(
                    "SELECT id, to_char(created_at AT TIME ZONE 'UTC', "
                    "'YYYY_MM') AS month FROM notifications"
                )
            )
        }
        rows = _rows_by_partition(connection, "notifications")
        assert rows[101] == f"notifications_{notification_months[101]}"
        assert rows[102] == f"notifications_{notification_months[102]}"
        assert rows[103] == "notifications_default"

        delivery_months = {
            int(row.id): row.month
            for row in connection.execute(
                sa.text(
                    "SELECT id, to_char(attempted_at AT TIME ZONE 'UTC', "
                    "'YYYY_MM') AS month FROM notification_deliveries"
                )
            )
        }
        delivery_rows = _rows_by_partition(connection, "notification_deliveries")
        assert delivery_rows[201] == f"notification_deliveries_{delivery_months[201]}"
        assert delivery_rows[202] == f"notification_deliveries_{delivery_months[202]}"
        assert delivery_rows[203] == "notification_deliveries_default"

        assert _linked_delivery_count(connection) == 3
        assert _linked_audit_count(connection) == 3
        _assert_constraints_and_indexes(connection)

        audit_fk_validated = connection.execute(
            sa.text(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conrelid = to_regclass('public.notification_audit') "
                "AND conname = 'notification_audit_notification_fk'"
            )
        ).scalar_one()
        assert audit_fk_validated is True

        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                invalid_write_timestamp = anchor + timedelta(days=12)
                connection.execute(
                    sa.text(
                        "INSERT INTO notifications "
                        "(id, created_at, user_id, title) "
                        "VALUES (999, :created_at, 999, 'invalid-user')"
                    ),
                    {"created_at": invalid_write_timestamp},
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO notification_deliveries "
                        "(id, attempted_at, notification_id, "
                        "notification_created_at, channel) "
                        "VALUES (999, :attempted_at, 999, :created_at, 'email')"
                    ),
                    {
                        "attempted_at": invalid_write_timestamp,
                        "created_at": invalid_write_timestamp,
                    },
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO notification_audit "
                        "(id, notification_id, notification_created_at) "
                        "VALUES (999, 999, :created_at)"
                    ),
                    {"created_at": invalid_write_timestamp},
                )


def _owned_foreign_key_identity(connection, relation: str, constraint_name: str):
    row = connection.execute(
        sa.text(
            "SELECT oid, conname, contype, convalidated, conparentid, confrelid, "
            "pg_get_constraintdef(oid, false) "
            "FROM pg_constraint WHERE conrelid = to_regclass(:relation) "
            "AND conname = :constraint_name"
        ),
        {"relation": f"public.{relation}", "constraint_name": constraint_name},
    ).one_or_none()
    return tuple(row) if row is not None else None


def _rows_for_relation(connection, relation: str) -> tuple[tuple[object, ...], ...]:
    rows = connection.execute(
        sa.text(f"SELECT * FROM public.{relation}")  # noqa: S608 -- generated test identifier
    ).all()
    return tuple(tuple(row) for row in rows)


def test_heap_conversion_refuses_stale_staging_relation_without_changes(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    table = f"aud038_heap_collision_{uuid4().hex[:8]}"
    stale = f"{table}_prepart_old"
    dependent = f"{table}_stale_dependent"

    with postgres_engine.begin() as connection:
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{table} ("
                "id bigint PRIMARY KEY, occurred_at timestamptz NOT NULL)"
            )
        )
        connection.execute(
            sa.text(f"INSERT INTO public.{table} VALUES (1, '2026-10-12T00:00:00Z')")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        )
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{stale} (id bigint PRIMARY KEY, marker text NOT NULL)"
            )
        )
        connection.execute(
            sa.text(f"INSERT INTO public.{stale} VALUES (7, 'preserve')")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        )
        fk_name = f"fk_{dependent}_stale"
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{dependent} ("
                "id bigint PRIMARY KEY, stale_id bigint NOT NULL, "
                f"CONSTRAINT {fk_name} FOREIGN KEY (stale_id) "
                f"REFERENCES public.{stale}(id) ON DELETE CASCADE)"
            )
        )
        connection.execute(sa.text(f"INSERT INTO public.{dependent} VALUES (9, 7)"))  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        before = {
            name: _parent_catalog_identity(connection, name)
            for name in (table, stale, dependent)
        }
        rows_before = {
            name: _rows_for_relation(connection, name)
            for name in (table, stale, dependent)
        }
        fk_before = _owned_foreign_key_identity(connection, dependent, fk_name)
        assert fk_before is not None
        with pytest.raises(RuntimeError, match=r"staging relation .* already exists"):
            migration._convert_to_partitioned(connection, table, "occurred_at")

        assert {
            name: _parent_catalog_identity(connection, name)
            for name in (table, stale, dependent)
        } == before
        assert {
            name: _rows_for_relation(connection, name)
            for name in (table, stale, dependent)
        } == rows_before
        assert migration._get_relkind(connection, table) == "r"
        assert migration._get_relkind(connection, stale) == "r"
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{table}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{stale}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{dependent}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )
        assert _owned_foreign_key_identity(connection, dependent, fk_name) == fk_before


def test_heap_conversion_rebinds_supported_composite_inbound_foreign_key(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    table = f"aud038_heap_composite_{uuid4().hex[:8]}"
    owner = f"{table}_owner"
    fk_name = f"fk_{table}_owner_parent"

    with postgres_engine.begin() as connection:
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{table} ("
                "id bigint NOT NULL, occurred_at timestamptz NOT NULL, "
                "PRIMARY KEY (id, occurred_at))"
            )
        )
        connection.execute(
            sa.text(f"INSERT INTO public.{table} VALUES (1, '2026-10-12T00:00:00Z')")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        )
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{owner} ("
                "id bigint PRIMARY KEY, parent_id bigint NOT NULL, "
                "parent_occurred_at timestamptz NOT NULL, "
                f"CONSTRAINT {fk_name} FOREIGN KEY (parent_id, parent_occurred_at) "
                f"REFERENCES public.{table}(id, occurred_at) ON DELETE CASCADE)"
            )
        )
        connection.execute(
            sa.text(f"INSERT INTO public.{owner} VALUES (2, 1, '2026-10-12T00:00:00Z')")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        )
        parent_rows_before = _rows_for_relation(connection, table)
        old_parent_oid = connection.execute(
            sa.text("SELECT to_regclass(:relation)::oid"),
            {"relation": f"public.{table}"},
        ).scalar_one()

        migration._convert_to_partitioned(connection, table, "occurred_at")

        new_parent_oid = connection.execute(
            sa.text("SELECT to_regclass(:relation)::oid"),
            {"relation": f"public.{table}"},
        ).scalar_one()
        assert new_parent_oid != old_parent_oid
        assert migration._get_relkind(connection, table) == "p"
        assert migration._get_relkind(connection, f"{table}_prepart_old") is None
        assert _rows_for_relation(connection, table) == parent_rows_before
        assert _rows_by_partition(connection, table) == {1: f"{table}_default"}
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{owner}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )

        fk = _owned_foreign_key_identity(connection, owner, fk_name)
        assert fk is not None
        assert fk[2:6] == (
            "f",
            True,
            0,
            new_parent_oid,
        )
        assert fk[6] == (
            f"FOREIGN KEY (parent_id, parent_occurred_at) "
            f"REFERENCES {table}(id, occurred_at) ON DELETE CASCADE"
        )
        primary_key = connection.execute(
            sa.text(
                "SELECT conname, convalidated, pg_get_constraintdef(oid, false) "
                "FROM pg_constraint WHERE conrelid = to_regclass(:relation) "
                "AND contype = 'p'"
            ),
            {"relation": f"public.{table}"},
        ).one()
        assert tuple(primary_key) == (
            f"{table}_pkey",
            True,
            "PRIMARY KEY (id, occurred_at)",
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        f"INSERT INTO public.{owner} "  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
                        "(id, parent_id, parent_occurred_at) "
                        "VALUES (3, 999, '2026-10-12T00:00:00Z')"
                    )
                )


def test_heap_conversion_rejects_id_only_inbound_foreign_key_before_changes(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    table = f"aud038_heap_idonly_{uuid4().hex[:8]}"
    owner = f"{table}_owner"
    fk_name = f"fk_{table}_owner_parent_id"

    with postgres_engine.begin() as connection:
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{table} ("
                "id bigint PRIMARY KEY, occurred_at timestamptz NOT NULL)"
            )
        )
        connection.execute(
            sa.text(f"INSERT INTO public.{table} VALUES (1, '2026-10-12T00:00:00Z')")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        )
        connection.execute(
            sa.text(
                f"CREATE TABLE public.{owner} ("
                "id bigint PRIMARY KEY, parent_id bigint NOT NULL, "
                f"CONSTRAINT {fk_name} FOREIGN KEY (parent_id) "
                f"REFERENCES public.{table}(id) ON DELETE CASCADE)"
            )
        )
        connection.execute(sa.text(f"INSERT INTO public.{owner} VALUES (2, 1)"))  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
        parent_before = _parent_catalog_identity(connection, table)
        owner_before = _parent_catalog_identity(connection, owner)
        parent_rows_before = _rows_for_relation(connection, table)
        owner_rows_before = _rows_for_relation(connection, owner)
        fk_before = _owned_foreign_key_identity(connection, owner, fk_name)

        with pytest.raises(RuntimeError, match="unsupported target columns"):
            migration._convert_to_partitioned(connection, table, "occurred_at")

        assert _parent_catalog_identity(connection, table) == parent_before
        assert _parent_catalog_identity(connection, owner) == owner_before
        assert _rows_for_relation(connection, table) == parent_rows_before
        assert _rows_for_relation(connection, owner) == owner_rows_before
        assert _owned_foreign_key_identity(connection, owner, fk_name) == fk_before
        assert migration._get_relkind(connection, table) == "r"
        assert migration._get_relkind(connection, f"{table}_prepart_old") is None
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{table}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text(f"SELECT count(*) FROM public.{owner}")  # noqa: S608 -- test identifiers use fixed prefixes and UUID hex
            ).scalar_one()
            == 1
        )


def test_full_migration_chain_preserves_uuid_notification_delivery_links(
    postgres_engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise UUID rows through partitioning, reconciliation, and HEAD."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

    from alembic import command
    from app.utils.uuid_v7 import generate_uuid7

    database_name = f"aud038_chain_{uuid4().hex}"
    quoted_database = postgres_engine.dialect.identifier_preparer.quote(database_name)
    database_created = False
    migration_engine: sa.Engine | None = None
    seeded_at = datetime.now(UTC)
    in_window_at = seeded_at.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    out_of_window_at = datetime(2000, 1, 15, 12, tzinfo=UTC)
    user_id = generate_uuid7(seeded_at)
    seeded_rows = (
        {
            "notification_id": generate_uuid7(in_window_at),
            "delivery_id": generate_uuid7(in_window_at),
            "created_at": in_window_at,
            "title": "AUD-038 in-window UUID fixture",
            "expected_partition": (
                f"notifications_{in_window_at:%Y_%m}",
                f"notification_deliveries_{in_window_at:%Y_%m}",
            ),
        },
        {
            "notification_id": generate_uuid7(out_of_window_at),
            "delivery_id": generate_uuid7(out_of_window_at),
            "created_at": out_of_window_at,
            "title": "AUD-038 out-of-window UUID fixture",
            "expected_partition": (
                "notifications_default",
                "notification_deliveries_default",
            ),
        },
    )
    rows_by_id = {row["notification_id"]: row for row in seeded_rows}

    def assert_rows_and_partitions(
        expected: dict[object, tuple[str, str]],
    ) -> None:
        assert migration_engine is not None
        with migration_engine.connect() as connection:
            metadata = sa.MetaData()
            notifications = sa.Table(
                "notifications", metadata, schema="public", autoload_with=connection
            )
            deliveries = sa.Table(
                "notification_deliveries",
                metadata,
                schema="public",
                autoload_with=connection,
            )
            joined = notifications.join(
                deliveries,
                sa.and_(
                    deliveries.c.notification_id == notifications.c.id,
                    deliveries.c.notification_created_at == notifications.c.created_at,
                ),
            )
            rows = (
                connection.execute(
                    sa.select(
                        notifications.c.id.label("notification_id"),
                        notifications.c.user_id,
                        notifications.c.title,
                        notifications.c.created_at,
                        deliveries.c.id.label("delivery_id"),
                        deliveries.c.notification_id.label("delivery_notification_id"),
                        deliveries.c.notification_created_at,
                        deliveries.c.channel,
                        deliveries.c.status,
                        deliveries.c.attempted_at,
                        sa.literal_column(
                            "notifications.tableoid::regclass::text"
                        ).label("notification_partition"),
                        sa.literal_column(
                            "notification_deliveries.tableoid::regclass::text"
                        ).label("delivery_partition"),
                    )
                    .select_from(joined)
                    .where(
                        notifications.c.user_id == user_id,
                        notifications.c.id.in_(tuple(rows_by_id)),
                    )
                    .order_by(notifications.c.id)
                )
                .mappings()
                .all()
            )
            assert len(rows) == len(seeded_rows)
            assert {row["notification_id"] for row in rows} == set(rows_by_id)
            for row in rows:
                seed = rows_by_id[row["notification_id"]]
                assert row["user_id"] == user_id
                assert row["title"] == seed["title"]
                assert row["created_at"] == seed["created_at"]
                assert row["delivery_id"] == seed["delivery_id"]
                assert row["notification_id"] == seed["notification_id"]
                assert row["delivery_notification_id"] == seed["notification_id"]
                assert row["notification_created_at"] == seed["created_at"]
                assert row["attempted_at"] == seed["created_at"]
                assert row["channel"] == "inapp"
                assert row["status"] == "delivered"
                actual = (
                    str(row["notification_partition"]).rsplit(".", 1)[-1],
                    str(row["delivery_partition"]).rsplit(".", 1)[-1],
                )
                assert actual == expected[row["notification_id"]]
            assert connection.execute(
                sa.select(sa.func.count())
                .select_from(notifications)
                .where(notifications.c.user_id == user_id)
            ).scalar_one() == len(seeded_rows)
            assert connection.execute(
                sa.select(sa.func.count())
                .select_from(deliveries)
                .where(deliveries.c.notification_id.in_(tuple(rows_by_id)))
            ).scalar_one() == len(seeded_rows)

    def assert_reconciled_contract() -> None:
        assert migration_engine is not None
        indexes = {
            "notifications": {
                "ix_notifications_created_at": ("created_at",),
                "ix_notifications_dedupe_key": ("dedupe_key",),
                "ix_notifications_dupe_check": (
                    "user_id",
                    "title",
                    "url",
                    "created_at",
                ),
                "ix_notifications_read": ("read",),
                "ix_notifications_read_at": ("read_at",),
                "ix_notifications_title": ("title",),
                "ix_notifications_type": ("type",),
                "ix_notifications_user_created": ("user_id", "created_at"),
                "ix_notifications_user_dedupe": ("user_id", "dedupe_key"),
                "ix_notifications_user_id": ("user_id",),
                "ix_notifications_user_id_read": ("user_id", "read"),
            },
            "notification_deliveries": {
                "ix_notification_deliveries_attempted_at": ("attempted_at",),
                "ix_notification_deliveries_channel": ("channel",),
                "ix_notification_deliveries_dedup": (
                    "notification_id",
                    "channel",
                    "subscription_id",
                ),
                "ix_notification_deliveries_delivered_at": ("delivered_at",),
                "ix_notification_deliveries_notif_channel": (
                    "notification_id",
                    "channel",
                ),
                "ix_notification_deliveries_notification_id": ("notification_id",),
                "ix_notification_deliveries_status": ("status",),
                "ix_notification_deliveries_subscription_id": ("subscription_id",),
            },
        }
        partition_keys = {
            "notifications": ("created_at", ("id", "created_at")),
            "notification_deliveries": ("attempted_at", ("id", "attempted_at")),
        }
        with migration_engine.connect() as connection:
            inspector = sa.inspect(connection)
            for table, (partition_key, primary_key) in partition_keys.items():
                pk = inspector.get_pk_constraint(table)
                assert pk["name"] == f"{table}_pkey"
                assert tuple(pk["constrained_columns"]) == primary_key
                partition_rows = connection.execute(
                    sa.text(
                        "SELECT part.partstrat, attr.attname "
                        "FROM pg_partitioned_table AS part "
                        "JOIN LATERAL unnest(part.partattrs) WITH ORDINALITY "
                        "AS key(attnum, ordinal) ON TRUE "
                        "JOIN pg_class AS rel ON rel.oid = part.partrelid "
                        "JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace "
                        "JOIN pg_attribute AS attr "
                        "ON attr.attrelid = rel.oid AND attr.attnum = key.attnum "
                        "WHERE rel.oid = to_regclass(:relation) "
                        "AND ns.nspname = 'public' ORDER BY key.ordinal"
                    ),
                    {"relation": f"public.{table}"},
                ).all()
                assert len(partition_rows) == 1
                strategy = partition_rows[0][0]
                if isinstance(strategy, bytes):
                    strategy = strategy.decode("ascii")
                assert str(strategy) == "r"
                assert partition_rows[0][1] == partition_key
                assert (
                    connection.execute(
                        sa.text(
                            "SELECT convalidated FROM pg_constraint "
                            "WHERE conrelid = to_regclass(:relation) "
                            "AND conname = :name AND contype = 'p'"
                        ),
                        {
                            "relation": f"public.{table}",
                            "name": f"{table}_pkey",
                        },
                    ).scalar_one()
                    is True
                )

                actual_indexes = {
                    index["name"]: tuple(index.get("column_names") or ())
                    for index in inspector.get_indexes(table)
                    if index.get("name")
                }
                for name, columns in indexes[table].items():
                    assert actual_indexes.get(name) == columns
                    assert (
                        connection.execute(
                            sa.text(
                                "SELECT idx.indisvalid FROM pg_index AS idx "
                                "WHERE idx.indexrelid = to_regclass(:index_name) "
                                "AND idx.indrelid = to_regclass(:relation)"
                            ),
                            {
                                "index_name": f"public.{name}",
                                "relation": f"public.{table}",
                            },
                        ).scalar_one_or_none()
                        is True
                    )

            foreign_keys = {
                "notifications": (("user_id",), "users", ("id",)),
                "notification_deliveries": (
                    ("notification_id", "notification_created_at"),
                    "notifications",
                    ("id", "created_at"),
                ),
            }
            for table, (
                columns,
                referred_table,
                referred_columns,
            ) in foreign_keys.items():
                root_foreign_keys = set(
                    connection.scalars(
                        sa.text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = to_regclass(:relation) "
                            "AND contype = 'f' AND conparentid = 0"
                        ),
                        {"relation": f"public.{table}"},
                    )
                )
                matches = [
                    fk
                    for fk in inspector.get_foreign_keys(table)
                    if tuple(fk.get("constrained_columns") or ()) == columns
                    and fk["name"] in root_foreign_keys
                ]
                assert len(matches) == 1
                fk = matches[0]
                assert fk["referred_table"] == referred_table
                assert tuple(fk["referred_columns"]) == referred_columns
                assert (
                    str((fk.get("options") or {}).get("ondelete", "")).upper()
                    == "CASCADE"
                )
                assert fk["name"] is not None
                assert (
                    connection.execute(
                        sa.text(
                            "SELECT convalidated FROM pg_constraint "
                            "WHERE conrelid = to_regclass(:relation) "
                            "AND conname = :name AND contype = 'f' AND conparentid = 0"
                        ),
                        {"relation": f"public.{table}", "name": fk["name"]},
                    ).scalar_one()
                    is True
                )

            unique_name = "uq_notification_delivery_once"
            unique_constraints = {
                item["name"]: tuple(item.get("column_names") or ())
                for item in inspector.get_unique_constraints("notification_deliveries")
                if item.get("name")
            }
            assert unique_constraints.get(unique_name) == (
                "notification_id",
                "channel",
                "subscription_id",
                "attempted_at",
            )
            assert (
                connection.execute(
                    sa.text(
                        "SELECT convalidated FROM pg_constraint "
                        "WHERE conrelid = to_regclass(:relation) "
                        "AND conname = :name AND contype = 'u'"
                    ),
                    {
                        "relation": "public.notification_deliveries",
                        "name": unique_name,
                    },
                ).scalar_one()
                is True
            )

    try:
        with postgres_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as admin:
            assert (
                admin.execute(
                    sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": database_name},
                ).scalar_one_or_none()
                is None
            )
            admin.exec_driver_sql(f"CREATE DATABASE {quoted_database}")
            database_created = True

        sync_url = postgres_engine.url.set(database=database_name)
        async_url = sync_url.set(drivername="postgresql+asyncpg").render_as_string(
            hide_password=False
        )
        migration_engine = sa.create_engine(sync_url)
        monkeypatch.setenv("DATABASE_URL", async_url)
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", async_url.replace("%", "%%"))

        command.upgrade(config, "202605300007")
        with migration_engine.begin() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision()
                == "202605300007"
            )
            for table_name, column_name in (
                ("users", "id"),
                ("notifications", "id"),
                ("notifications", "user_id"),
                ("notification_deliveries", "id"),
                ("notification_deliveries", "notification_id"),
            ):
                column_types = {
                    column["name"]: column["type"]
                    for column in sa.inspect(connection).get_columns(
                        table_name, schema="public"
                    )
                }
                assert isinstance(column_types[column_name], PostgreSQLUUID)

            for partition_parent, partition_key in (
                ("notifications", "created_at"),
                ("notification_deliveries", "attempted_at"),
            ):
                _ensure_historical_default_partition(
                    connection, partition_parent, partition_key
                )

            metadata = sa.MetaData()
            users = sa.Table(
                "users", metadata, schema="public", autoload_with=connection
            )
            notifications = sa.Table(
                "notifications", metadata, schema="public", autoload_with=connection
            )
            deliveries = sa.Table(
                "notification_deliveries",
                metadata,
                schema="public",
                autoload_with=connection,
            )
            fixture_digest = "not-used-for-authentication"
            connection.execute(
                users.insert().values(
                    id=user_id,
                    email=f"aud038-{uuid4().hex}@example.invalid",
                    hashed_password=fixture_digest,
                    role="student",
                    is_active=True,
                    mfa_required=False,
                )
            )
            for row in seeded_rows:
                connection.execute(
                    notifications.insert().values(
                        id=row["notification_id"],
                        user_id=user_id,
                        title=row["title"],
                        read=False,
                        created_at=row["created_at"],
                    )
                )
                connection.execute(
                    deliveries.insert().values(
                        id=row["delivery_id"],
                        notification_id=row["notification_id"],
                        notification_created_at=row["created_at"],
                        channel="inapp",
                        status="delivered",
                        attempted_at=row["created_at"],
                    )
                )

        assert_rows_and_partitions(
            {
                row["notification_id"]: (
                    "notifications_default",
                    "notification_deliveries_default",
                )
                for row in seeded_rows
            }
        )
        command.upgrade(config, "202607020001")
        assert_rows_and_partitions(
            {row["notification_id"]: row["expected_partition"] for row in seeded_rows}
        )

        command.upgrade(config, "202608270003")
        with migration_engine.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision()
                == "202608270003"
            )
        assert_reconciled_contract()
        assert_rows_and_partitions(
            {row["notification_id"]: row["expected_partition"] for row in seeded_rows}
        )

        command.upgrade(config, "head")
        script = ScriptDirectory.from_config(config)
        with migration_engine.connect() as connection:
            assert tuple(
                sorted(MigrationContext.configure(connection).get_current_heads())
            ) == tuple(sorted(script.get_heads()))
        assert_reconciled_contract()
        assert_rows_and_partitions(
            {row["notification_id"]: row["expected_partition"] for row in seeded_rows}
        )
    finally:
        if migration_engine is not None:
            migration_engine.dispose()
        if database_created:
            with postgres_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as admin:
                admin.exec_driver_sql(f"DROP DATABASE {quoted_database}")
