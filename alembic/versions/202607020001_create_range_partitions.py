"""Create monthly range partitions for all RANGE-partitioned tables.

On a fresh PostgreSQL schema (CI), the RANGE-partitioned tables
(data_access_logs, notifications, notification_deliveries,
failed_login_attempts) may be created as regular heap tables ('relkind=r')
because the conversion migration (6a898bba5589) skips on fresh schemas.

This migration handles both cases:
  • relkind='p'  — already partitioned; create any missing partitions.
  • relkind='r'  — regular table; convert in-place (rename → create
                   partitioned → DEFAULT → copy data → drop old),
                   then create monthly partitions.

Partitions created:
  1. A DEFAULT partition on each table (absorbs overflow rows).
  2. Monthly partitions covering MONTHS_BACK months back and MONTHS_FORWARD
     months forward from the migration timestamp.

All CREATE TABLE statements use IF NOT EXISTS — the migration is idempotent.

Revision ID: 202607020001
Revises: 202605300007
Create Date: 2026-07-02
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "202607020001"
down_revision = "202605300007"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic")

# Each entry: (table_name, partition_key_column).
_PARTITIONED_TABLES: list[tuple[str, str]] = [
    ("data_access_logs", "created_at"),
    ("notifications", "created_at"),
    ("notification_deliveries", "attempted_at"),
    ("failed_login_attempts", "attempted_at"),
]

_MONTHS_BACK = 6
_MONTHS_FORWARD = 18


def _add_months(dt: datetime, months: int) -> datetime:
    """Return a new datetime shifted by *months* calendar months."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def _get_relkind(conn, table_name: str) -> str | None:
    """Return pg_class.relkind for *table_name* in the public schema, or None."""
    row = conn.execute(
        sa.text(
            "SELECT c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :tbl AND n.nspname = 'public'"
        ),
        {"tbl": table_name},
    ).fetchone()
    if not row:
        return None
    # asyncpg exposes PostgreSQL's ``char`` catalog type as a one-byte
    # ``bytes`` value, while psycopg exposes a string.  Normalize both forms
    # before comparing with the documented relkind codes below; otherwise a
    # live partitioned table is misclassified and the migration silently
    # skips its partition reconciliation.
    value = row[0]
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def _existing_partition_names(conn, parent_table: str) -> set[str]:
    """Return the set of child relation names that inherit from *parent_table*."""
    rows = conn.execute(
        sa.text(
            "SELECT child.relname "
            "FROM pg_inherits "
            "JOIN pg_class child  ON pg_inherits.inhrelid  = child.oid "
            "JOIN pg_class parent ON pg_inherits.inhparent = parent.oid "
            "JOIN pg_namespace n  ON n.oid = parent.relnamespace "
            "WHERE parent.relname = :tbl AND n.nspname = 'public' "
            "AND parent.relkind = 'p' AND child.relispartition"
        ),
        {"tbl": parent_table},
    ).fetchall()
    return {r[0] for r in rows}


def _range_predicate(
    partition_key: str,
    ranges: list[tuple[datetime, datetime]],
) -> tuple[sa.sql.elements.ColumnElement[bool], dict[str, datetime]]:
    """Build a SQLAlchemy predicate for the internally generated month ranges."""
    predicates: list[sa.sql.elements.ColumnElement[bool]] = []
    parameters: dict[str, datetime] = {}
    column = sa.column(partition_key)
    for index, (start, end) in enumerate(ranges):
        lower = f"range_start_{index}"
        upper = f"range_end_{index}"
        predicates.append(
            sa.and_(
                column >= sa.bindparam(lower),
                column < sa.bindparam(upper),
            )
        )
        parameters[lower] = start
        parameters[upper] = end
    return sa.or_(*predicates), parameters


def _count_rows_for_ranges(
    conn,
    table_name: str,
    partition_key: str,
    ranges: list[tuple[datetime, datetime]],
) -> int:
    """Count rows inside the requested ranges using PostgreSQL-bound datetimes."""
    if not ranges:
        return 0
    predicate, parameters = _range_predicate(partition_key, ranges)
    table = sa.table(table_name, schema="public")
    row = conn.execute(
        sa.select(sa.func.count()).select_from(table).where(predicate),
        parameters,
    ).scalar()
    return int(row or 0)


def _get_column_definitions(conn, table_name: str) -> str:
    """Build a parenthesised column-definition list from pg_catalog.

    Returns a string suitable for insertion into:
        CREATE TABLE new_table ( <result> ) PARTITION BY RANGE (col)

    Only basic attributes are reproduced (name, type, NOT NULL, DEFAULT).
    Constraints and indexes are intentionally omitted because:
      - PRIMARY KEY on a RANGE-partitioned table must include the partition key,
        which may differ from the legacy single-column PK.
      - Indexes are recreated by later migrations or already exist on the new
        partitioned parent after data is copied.
    """
    rows = conn.execute(
        sa.text(
            """
            SELECT
                a.attname                                      AS col_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS col_type,
                a.attnotnull                                   AS not_null,
                pg_get_expr(d.adbin, d.adrelid)               AS col_default
            FROM   pg_attribute  a
            JOIN   pg_class      c ON c.oid = a.attrelid
            JOIN   pg_namespace  n ON n.oid = c.relnamespace
            LEFT   JOIN pg_attrdef d
                   ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE  c.relname    = :tbl
              AND  n.nspname    = 'public'
              AND  a.attnum     > 0
              AND  NOT a.attisdropped
            ORDER BY a.attnum
            """
        ),
        {"tbl": table_name},
    ).fetchall()

    parts = []
    for col_name, col_type, not_null, col_default in rows:
        definition = f'"{col_name}" {col_type}'
        if not_null:
            definition += " NOT NULL"
        if col_default:
            definition += f" DEFAULT {col_default}"
        parts.append(definition)

    return ",\n    ".join(parts)


def _convert_to_partitioned(conn, table_name: str, partition_key: str) -> None:
    """Convert a regular heap while preserving compatible inbound foreign keys.

    A stale staging relation is treated as operator-owned data and is never
    overwritten. Inbound keys must reference the partition-compatible key
    ``(id, partition_key)`` because a partitioned parent cannot provide a
    global unique constraint on an id-only target.
    """
    old_name = f"{table_name}_prepart_old"
    preparer = conn.dialect.identifier_preparer

    def qualified(name: str) -> str:
        return f"{preparer.quote_schema('public')}.{preparer.quote(name)}"

    if _get_relkind(conn, old_name) is not None:
        raise RuntimeError(
            f"Cannot convert {table_name}: staging relation {old_name} already exists"
        )

    parent_relation = qualified(table_name)
    conn.execute(sa.text(f"LOCK TABLE {parent_relation} IN ACCESS EXCLUSIVE MODE"))
    if _get_relkind(conn, old_name) is not None:
        raise RuntimeError(
            f"Cannot convert {table_name}: staging relation {old_name} already exists"
        )

    incoming_foreign_keys = _incoming_foreign_keys(conn, table_name)
    expected_referenced_columns = ("id", partition_key)
    for foreign_key in incoming_foreign_keys:
        if tuple(foreign_key["referenced_columns"]) != expected_referenced_columns:
            raise RuntimeError(
                f"Cannot convert {table_name}: inbound foreign key "
                f"{foreign_key['constraint_name']} references unsupported target columns"
            )

    _lock_foreign_key_relations(conn, incoming_foreign_keys)
    locked_foreign_keys = _incoming_foreign_keys(conn, table_name)
    if locked_foreign_keys != incoming_foreign_keys:
        raise RuntimeError(
            f"Inbound foreign keys changed while preparing to convert {table_name}"
        )

    logger.info("Converting %s from relkind='r' to partitioned", table_name)
    col_defs = _get_column_definitions(conn, table_name)

    _drop_incoming_foreign_keys(conn, incoming_foreign_keys)
    conn.execute(
        sa.text(
            "-- The original heap stays ACCESS EXCLUSIVE locked while its name is "
            "moved aside so the populated partitioned replacement can take the "
            "public name in this same transaction.\n"
            "-- squawk-ignore renaming-table\n"
            f"ALTER TABLE {parent_relation} RENAME TO {preparer.quote(old_name)}"
        )
    )
    conn.execute(
        sa.text(
            f"CREATE TABLE {parent_relation} (\n    {col_defs}\n) "
            f"PARTITION BY RANGE ({preparer.quote(partition_key)})"
        )
    )

    default_partition = f"{table_name}_default"
    qualified_default = qualified(default_partition)
    conn.execute(
        sa.text(
            f"CREATE TABLE IF NOT EXISTS {qualified_default} "
            f"PARTITION OF {parent_relation} DEFAULT"
        )
    )

    # Copy rows while FK owners are locked and their root constraints are absent.
    qualified_old = qualified(old_name)
    conn.execute(
        sa.text(f"INSERT INTO {parent_relation} SELECT * FROM {qualified_old}")  # noqa: S608 -- identifiers are quoted by the dialect preparer
    )
    # RESTRICT is intentional: untracked dependencies must abort and roll back.
    conn.execute(
        sa.text(
            "-- The replacement has received the heap rows; keep default RESTRICT "
            "so any dependency not represented by the captured FK set aborts and "
            "rolls back the rename, copy, and FK changes.\n"
            "-- squawk-ignore ban-drop-table\n"
            f"DROP TABLE {qualified_old}"
        )
    )

    if incoming_foreign_keys:
        primary_key_name = preparer.quote(f"{table_name}_pkey")
        id_column = preparer.quote("id")
        partition_column = preparer.quote(partition_key)
        conn.execute(
            sa.text(
                f"ALTER TABLE {parent_relation} ADD CONSTRAINT {primary_key_name} "
                f"PRIMARY KEY ({id_column}, {partition_column})"
            )
        )
        _restore_incoming_foreign_keys(conn, incoming_foreign_keys)

    logger.info("Conversion of %s complete", table_name)


def _incoming_foreign_keys(conn, referenced_table: str) -> list[dict[str, object]]:
    """Snapshot validated top-level FKs that reference this table or a partition."""
    rows = (
        conn.execute(
            sa.text(
                """
            WITH RECURSIVE referenced_relations(oid) AS (
                SELECT relation.oid
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE relation.relname = :table AND namespace.nspname = 'public'
                UNION
                SELECT inheritance.inhrelid
                FROM pg_inherits AS inheritance
                JOIN referenced_relations AS referenced
                  ON referenced.oid = inheritance.inhparent
            ),
            matching_constraints(oid) AS (
                SELECT constraint_row.oid
                FROM pg_constraint AS constraint_row
                JOIN referenced_relations AS referenced
                  ON referenced.oid = constraint_row.confrelid
                WHERE constraint_row.contype = 'f'
            ),
            constraint_ancestry(matched_oid, ancestor_oid) AS (
                SELECT oid, oid FROM matching_constraints
                UNION
                SELECT ancestry.matched_oid, parent_constraint.oid
                FROM constraint_ancestry AS ancestry
                JOIN pg_constraint AS current_constraint
                  ON current_constraint.oid = ancestry.ancestor_oid
                JOIN pg_constraint AS parent_constraint
                  ON parent_constraint.oid = current_constraint.conparentid
            ),
            root_constraints(oid) AS (
                SELECT DISTINCT ancestry.ancestor_oid
                FROM constraint_ancestry AS ancestry
                JOIN pg_constraint AS root_constraint
                  ON root_constraint.oid = ancestry.ancestor_oid
                WHERE root_constraint.conparentid = 0
            )
            SELECT constraint_row.oid AS constraint_oid,
                   constraint_row.conrelid AS relation_oid,
                   constraint_row.conname AS constraint_name,
                   constraint_row.convalidated AS validated,
                   constraint_row.coninhcount AS inheritance_count,
                   relation.relkind AS relation_kind,
                   namespace.nspname AS schema_name,
                   relation.relname AS relation_name,
                   pg_get_constraintdef(constraint_row.oid, false) AS definition,
                   ARRAY(
                       SELECT referenced_attribute.attname
                       FROM unnest(constraint_row.confkey) WITH ORDINALITY
                            AS referenced_column(attnum, ordinal)
                       JOIN pg_attribute AS referenced_attribute
                         ON referenced_attribute.attrelid = constraint_row.confrelid
                        AND referenced_attribute.attnum = referenced_column.attnum
                       ORDER BY referenced_column.ordinal
                   ) AS referenced_columns
            FROM root_constraints AS root
            JOIN pg_constraint AS constraint_row ON constraint_row.oid = root.oid
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            ORDER BY constraint_row.conrelid, constraint_row.oid
            """
            ),
            {"table": referenced_table},
        )
        .mappings()
        .all()
    )

    foreign_keys: list[dict[str, object]] = []
    for row in rows:
        if not row["validated"]:
            raise RuntimeError(
                f"Cannot redistribute {referenced_table}: inbound foreign key "
                f"{row['constraint_name']} is not validated"
            )
        if int(row["inheritance_count"] or 0) != 0:
            raise RuntimeError(
                f"Cannot redistribute {referenced_table}: inbound foreign key "
                f"{row['constraint_name']} uses unsupported table inheritance"
            )
        relation_kind = row["relation_kind"]
        if isinstance(relation_kind, bytes):
            relation_kind = relation_kind.decode("ascii")
        else:
            relation_kind = str(relation_kind)
        if relation_kind not in {"r", "p"}:
            raise RuntimeError(
                f"Cannot redistribute {referenced_table}: inbound foreign key "
                f"{row['constraint_name']} has unsupported relation kind"
            )
        foreign_keys.append(
            {
                "constraint_oid": int(row["constraint_oid"]),
                "relation_oid": int(row["relation_oid"]),
                "constraint_name": str(row["constraint_name"]),
                "relation_kind": relation_kind,
                "schema_name": str(row["schema_name"]),
                "relation_name": str(row["relation_name"]),
                "definition": str(row["definition"]),
                "referenced_columns": tuple(
                    str(column) for column in row["referenced_columns"] or ()
                ),
            }
        )
    return foreign_keys


def _lock_foreign_key_relations(conn, foreign_keys: list[dict[str, object]]) -> None:
    """Lock FK owners in stable order without waiting into a lock cycle."""
    preparer = conn.dialect.identifier_preparer
    relations = {
        (
            int(foreign_key["relation_oid"]),
            str(foreign_key["schema_name"]),
            str(foreign_key["relation_name"]),
        )
        for foreign_key in foreign_keys
    }
    for _oid, schema_name, relation_name in sorted(relations):
        qualified_name = (
            f"{preparer.quote_schema(schema_name)}.{preparer.quote(relation_name)}"
        )
        conn.execute(
            sa.text(f"LOCK TABLE {qualified_name} IN ACCESS EXCLUSIVE MODE NOWAIT")
        )


def _drop_incoming_foreign_keys(conn, foreign_keys: list[dict[str, object]]) -> None:
    """Drop captured FK roots; PostgreSQL removes their internal partition clones."""
    preparer = conn.dialect.identifier_preparer
    for foreign_key in foreign_keys:
        qualified_name = (
            f"{preparer.quote_schema(str(foreign_key['schema_name']))}."
            f"{preparer.quote(str(foreign_key['relation_name']))}"
        )
        constraint_name = preparer.quote(str(foreign_key["constraint_name"]))
        conn.execute(
            sa.text(f"ALTER TABLE {qualified_name} DROP CONSTRAINT {constraint_name}")
        )


def _restore_incoming_foreign_keys(conn, foreign_keys: list[dict[str, object]]) -> None:
    """Restore captured FK definitions and require validation before commit."""
    preparer = conn.dialect.identifier_preparer
    for foreign_key in foreign_keys:
        qualified_name = (
            f"{preparer.quote_schema(str(foreign_key['schema_name']))}."
            f"{preparer.quote(str(foreign_key['relation_name']))}"
        )
        constraint_name = preparer.quote(str(foreign_key["constraint_name"]))
        definition = str(foreign_key["definition"])
        add_constraint = (
            f"ALTER TABLE {qualified_name} ADD CONSTRAINT "
            f"{constraint_name} {definition}"
        )
        if foreign_key["relation_kind"] == "p":
            # PostgreSQL 17 does not permit NOT VALID FKs on partitioned tables.
            conn.execute(sa.text(add_constraint))
        else:
            conn.execute(sa.text(f"{add_constraint} NOT VALID"))
            conn.execute(
                sa.text(
                    f"ALTER TABLE {qualified_name} VALIDATE CONSTRAINT "
                    f"{constraint_name}"
                )
            )

        restored = (
            conn.execute(
                sa.text(
                    "SELECT convalidated, conparentid, "
                    "pg_get_constraintdef(oid, false) AS definition "
                    "FROM pg_constraint "
                    "WHERE conrelid = :relation_oid AND conname = :constraint_name "
                    "AND contype = 'f'"
                ),
                {
                    "relation_oid": foreign_key["relation_oid"],
                    "constraint_name": foreign_key["constraint_name"],
                },
            )
            .mappings()
            .one_or_none()
        )
        if (
            restored is None
            or not restored["convalidated"]
            or int(restored["conparentid"] or 0) != 0
            or restored["definition"] != definition
        ):
            raise RuntimeError(
                f"Could not restore validated inbound foreign key "
                f"{foreign_key['constraint_name']}"
            )


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite and other dialects have no RANGE partitioning support.
        return

    # Keep catalog inspection, ACCESS EXCLUSIVE locks, and DDL within the
    # transaction-local migration budgets used by the other schema revisions.
    conn.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    conn.execute(sa.text("SET LOCAL statement_timeout = '60s'"))

    anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for table, partition_key in _PARTITIONED_TABLES:
        relkind = _get_relkind(conn, table)
        logger.info("Table %s: relkind=%r", table, relkind)

        if relkind is None:
            logger.info("Table %s does not exist — skipping", table)
            continue

        if relkind == "r":
            # Regular heap table: convert it to a RANGE-partitioned table first.
            _convert_to_partitioned(conn, table, partition_key)
            # After conversion the table is partitioned; fetch fresh state.
            relkind = _get_relkind(conn, table)

        if relkind != "p":
            # Unexpected state (view, materialized view, …) — bail out safely.
            logger.warning(
                "Table %s has relkind=%r after conversion attempt; skipping.",
                table,
                relkind,
            )
            continue

        # Partition DDL must serialize with writers before inspecting DEFAULT.
        # The lock is retained through detach, redistribution, and reattachment.
        conn.execute(sa.text(f'LOCK TABLE "public"."{table}" IN ACCESS EXCLUSIVE MODE'))
        existing = _existing_partition_names(conn, table)
        logger.info("Table %s existing partitions: %s", table, sorted(existing))

        # DEFAULT partition — absorbs rows outside the monthly coverage window.
        default_partition = f"{table}_default"
        if default_partition not in existing:
            logger.info("Creating DEFAULT partition %s", default_partition)
            conn.execute(
                sa.text(
                    f'CREATE TABLE IF NOT EXISTS "public"."{default_partition}" '
                    f'PARTITION OF "public"."{table}" DEFAULT'
                )
            )
            existing.add(default_partition)

        # Build only missing ranges first. PostgreSQL rejects adding a range
        # partition while matching rows remain in DEFAULT.
        monthly_partitions: list[tuple[str, datetime, datetime]] = []
        for offset in range(-_MONTHS_BACK, _MONTHS_FORWARD + 1):
            start = _add_months(anchor, offset)
            end = _add_months(anchor, offset + 1)
            suffix = start.strftime("%Y_%m")
            partition_name = f"{table}_{suffix}"
            if partition_name not in existing:
                monthly_partitions.append((partition_name, start, end))

        if not monthly_partitions:
            continue

        ranges = [(start, end) for _name, start, end in monthly_partitions]
        rows_to_redistribute = _count_rows_for_ranges(
            conn, default_partition, partition_key, ranges
        )
        redistribute_default = rows_to_redistribute > 0
        if redistribute_default:
            # Pausing inbound checks is safe only while every FK owner is locked
            # and the exact validated definitions are restored before commit.
            incoming_foreign_keys = _incoming_foreign_keys(conn, table)
            _lock_foreign_key_relations(conn, incoming_foreign_keys)
            locked_foreign_keys = _incoming_foreign_keys(conn, table)
            if locked_foreign_keys != incoming_foreign_keys:
                raise RuntimeError(
                    "Inbound foreign keys changed while preparing to redistribute "
                    f"{table}"
                )
            _drop_incoming_foreign_keys(conn, incoming_foreign_keys)

            # Detach the same DEFAULT relation so its rows can be redistributed
            # without deleting referenced rows visible to inbound foreign keys.
            conn.execute(
                sa.text(
                    f'ALTER TABLE "public"."{table}" '
                    f'DETACH PARTITION "public"."{default_partition}"'
                )
            )

        for partition_name, start, end in monthly_partitions:
            start_iso = start.strftime("%Y-%m-%d %H:%M:%S+00")
            end_iso = end.strftime("%Y-%m-%d %H:%M:%S+00")
            logger.info(
                "Creating partition %s [%s, %s)", partition_name, start_iso, end_iso
            )
            conn.execute(
                sa.text(
                    f'CREATE TABLE IF NOT EXISTS "public"."{partition_name}" '
                    f'PARTITION OF "public"."{table}" '
                    f"FOR VALUES FROM ('{start_iso}') TO ('{end_iso}')"
                )
            )

        if redistribute_default:
            predicate, parameters = _range_predicate(partition_key, ranges)
            metadata = sa.MetaData()
            parent_relation = sa.Table(
                table,
                metadata,
                schema="public",
                autoload_with=conn,
            )
            default_relation = sa.Table(
                default_partition,
                metadata,
                schema="public",
                autoload_with=conn,
            )
            column_names = [column.name for column in parent_relation.columns]
            conn.execute(
                sa.insert(parent_relation).from_select(
                    column_names,
                    sa.select(
                        *(
                            default_relation.c[column_name]
                            for column_name in column_names
                        )
                    ).where(predicate),
                ),
                parameters,
            )
            conn.execute(
                sa.delete(default_relation).where(predicate),
                parameters,
            )
            remaining = _count_rows_for_ranges(
                conn, default_partition, partition_key, ranges
            )
            if remaining:
                raise RuntimeError(
                    f"Could not redistribute all matching rows from {default_partition}"
                )

            conn.execute(
                sa.text(
                    f'ALTER TABLE "public"."{table}" '
                    f'ATTACH PARTITION "public"."{default_partition}" DEFAULT'
                )
            )
            redistributed = _count_rows_for_ranges(conn, table, partition_key, ranges)
            if redistributed != rows_to_redistribute:
                raise RuntimeError(
                    f"Redistribution row count changed for {table}: "
                    f"expected {rows_to_redistribute}, found {redistributed}"
                )
            _restore_incoming_foreign_keys(conn, incoming_foreign_keys)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for table, _key in _PARTITIONED_TABLES:
        if _get_relkind(conn, table) != "p":
            continue

        for offset in range(-_MONTHS_BACK, _MONTHS_FORWARD + 1):
            start = _add_months(anchor, offset)
            suffix = start.strftime("%Y_%m")
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}_{suffix}"))

        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}_default"))
