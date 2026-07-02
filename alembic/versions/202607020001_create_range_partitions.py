"""Create monthly range partitions for all RANGE-partitioned tables.

On a fresh PostgreSQL schema (e.g. CI), the RANGE-partitioned tables
(data_access_logs, notifications, notification_deliveries,
failed_login_attempts) are created with no partitions at all.  Any
INSERT immediately fails with:

    no partition of relation "<table>" found for row

This migration creates:
  1. A DEFAULT partition on each table (catches any overflow row).
  2. Monthly partitions covering 6 months back and 18 months forward
     from the migration timestamp, so CI and production always have a
     live partition for the current month.

The operation is idempotent — each CREATE TABLE uses IF NOT EXISTS.

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

# Partitioned tables and the column used as the partition key.
_PARTITIONED_TABLES: list[tuple[str, str]] = [
    ("data_access_logs", "created_at"),
    ("notifications", "created_at"),
    ("notification_deliveries", "attempted_at"),
    ("failed_login_attempts", "attempted_at"),
]

# Rolling window: months back and forward from the migration date.
_MONTHS_BACK = 6
_MONTHS_FORWARD = 18


def _add_months(dt: datetime, months: int) -> datetime:
    """Return a new datetime shifted by *months* calendar months."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def _get_relkind(conn, table_name: str) -> str | None:
    """Return pg_class.relkind for *table_name* or None if absent."""
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
            "JOIN pg_class child ON pg_inherits.inhrelid  = child.oid "
            "JOIN pg_class parent ON pg_inherits.inhparent = parent.oid "
            "JOIN pg_namespace n  ON n.oid = parent.relnamespace "
            "WHERE parent.relname = :tbl AND n.nspname = 'public'"
        ),
        {"tbl": parent_table},
    ).fetchall()
    return {r[0] for r in rows}


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite and other dialects don't support RANGE partitioning.
        return

    anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for table, _key in _PARTITIONED_TABLES:
        relkind = _get_relkind(conn, table)
        logger.info("Table %s: relkind=%r", table, relkind)

        if relkind is None:
            logger.info("Table %s does not exist — skipping", table)
            continue

        if relkind != "p":
            # Table exists but is NOT a partitioned table (e.g. regular heap
            # after a batch_alter_table rebuild).  We cannot attach range
            # partitions to a non-partitioned parent.  Log and skip — the
            # DEFAULT-partition strategy only works on partitioned parents.
            logger.warning(
                "Table %s exists but relkind=%r (expected 'p'). "
                "Partitions cannot be created.",
                table,
                relkind,
            )
            continue

        existing = _existing_partition_names(conn, table)
        logger.info("Table %s already has partitions: %s", table, existing)

        # 1. DEFAULT partition — absorbs any row that misses a range partition.
        default_partition = f"{table}_default"
        if default_partition not in existing:
            logger.info("Creating DEFAULT partition %s", default_partition)
            conn.execute(
                sa.text(
                    f"CREATE TABLE IF NOT EXISTS {default_partition} "
                    f"PARTITION OF {table} DEFAULT"
                )
            )
        else:
            logger.info("DEFAULT partition %s already exists", default_partition)

        # 2. Monthly range partitions: MONTHS_BACK ago … MONTHS_FORWARD ahead.
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
            partition_name = f"{table}_{suffix}"
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {partition_name}"))

        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}_default"))
