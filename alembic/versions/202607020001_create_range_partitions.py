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
    return row[0] if row else None


def _existing_partition_names(conn, parent_table: str) -> set[str]:
    """Return the set of child relation names that inherit from *parent_table*."""
    rows = conn.execute(
        sa.text(
            "SELECT child.relname "
            "FROM pg_inherits "
            "JOIN pg_class child  ON pg_inherits.inhrelid  = child.oid "
            "JOIN pg_class parent ON pg_inherits.inhparent = parent.oid "
            "JOIN pg_namespace n  ON n.oid = parent.relnamespace "
            "WHERE parent.relname = :tbl AND n.nspname = 'public'"
        ),
        {"tbl": parent_table},
    ).fetchall()
    return {r[0] for r in rows}


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
    """Convert a regular heap table to a RANGE-partitioned table in-place.

    Strategy (safe for tables with or without data):
      1. Rename the existing table to <table>_prepart_old.
      2. Create a new RANGE-partitioned table with identical columns.
      3. Create a DEFAULT partition to absorb all existing rows.
      4. Copy all rows from the old table into the new partitioned one.
      5. Drop the old table.

    Constraints (FK, PK, indexes) are not reproduced — they are managed by
    other migrations.  The DEFAULT partition ensures no INSERT fails while
    the monthly-partition loop runs immediately after.
    """
    old_name = f"{table_name}_prepart_old"

    # Guard: if a previous interrupted run left the old table, drop it.
    conn.execute(sa.text(f"DROP TABLE IF EXISTS {old_name} CASCADE"))

    logger.info("Converting %s from relkind='r' to partitioned", table_name)

    col_defs = _get_column_definitions(conn, table_name)

    conn.execute(sa.text(f"ALTER TABLE {table_name} RENAME TO {old_name}"))
    conn.execute(
        sa.text(
            f"CREATE TABLE {table_name} (\n    {col_defs}\n) "
            f"PARTITION BY RANGE ({partition_key})"
        )
    )

    default_partition = f"{table_name}_default"
    conn.execute(
        sa.text(
            f"CREATE TABLE IF NOT EXISTS {default_partition} "
            f"PARTITION OF {table_name} DEFAULT"
        )
    )

    # Copy existing data (typically empty on CI; minimal on production).
    conn.execute(sa.text(f"INSERT INTO {table_name} SELECT * FROM {old_name}"))  # noqa: S608
    conn.execute(sa.text(f"DROP TABLE {old_name}"))

    logger.info("Conversion of %s complete", table_name)


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite and other dialects have no RANGE partitioning support.
        return

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

        existing = _existing_partition_names(conn, table)
        logger.info("Table %s existing partitions: %s", table, sorted(existing))

        # DEFAULT partition — absorbs any row that misses a range partition.
        default_partition = f"{table}_default"
        if default_partition not in existing:
            logger.info("Creating DEFAULT partition %s", default_partition)
            conn.execute(
                sa.text(
                    f"CREATE TABLE IF NOT EXISTS {default_partition} "
                    f"PARTITION OF {table} DEFAULT"
                )
            )

        # Monthly range partitions: MONTHS_BACK ago … MONTHS_FORWARD ahead.
        for offset in range(-_MONTHS_BACK, _MONTHS_FORWARD + 1):
            start = _add_months(anchor, offset)
            end = _add_months(anchor, offset + 1)
            suffix = start.strftime("%Y_%m")
            partition_name = f"{table}_{suffix}"

            if partition_name not in existing:
                start_iso = start.strftime("%Y-%m-%d %H:%M:%S+00")
                end_iso = end.strftime("%Y-%m-%d %H:%M:%S+00")
                logger.info(
                    "Creating partition %s [%s, %s)", partition_name, start_iso, end_iso
                )
                conn.execute(
                    sa.text(
                        f"CREATE TABLE IF NOT EXISTS {partition_name} "
                        f"PARTITION OF {table} "
                        f"FOR VALUES FROM ('{start_iso}') "
                        f"TO ('{end_iso}')"
                    )
                )


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
