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

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "202607020001"
down_revision = "202605300007"
branch_labels = None
depends_on = None

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


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :tbl AND n.nspname = 'public')"
        ),
        {"tbl": table_name},
    )
    return bool(result.scalar())


def _is_partitioned(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :tbl AND n.nspname = 'public'"
        ),
        {"tbl": table_name},
    )
    row = result.fetchone()
    # 'p' = partitioned table in pg_class
    return row is not None and row[0] == "p"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite and other dialects don't support RANGE partitioning —
        # nothing to do.
        return

    anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for table, _key in _PARTITIONED_TABLES:
        if not _table_exists(conn, table):
            continue  # table hasn't been created yet — skip safely
        if not _is_partitioned(conn, table):
            continue  # legacy non-partitioned table — handled elsewhere

        # 1. DEFAULT partition — absorbs any row that misses a range partition.
        default_partition = f"{table}_default"
        op.execute(
            sa.text(
                f"CREATE TABLE IF NOT EXISTS {default_partition} "
                f"PARTITION OF {table} DEFAULT"
            )
        )

        # 2. Monthly range partitions: MONTHS_BACK ago … MONTHS_FORWARD ahead.
        for offset in range(-_MONTHS_BACK, _MONTHS_FORWARD + 1):
            start = _add_months(anchor, offset)
            end = _add_months(anchor, offset + 1)
            suffix = start.strftime("%Y_%m")
            partition_name = f"{table}_{suffix}"

            op.execute(
                sa.text(
                    f"CREATE TABLE IF NOT EXISTS {partition_name} "
                    f"PARTITION OF {table} "
                    f"FOR VALUES FROM ('{start.isoformat()}') "
                    f"TO ('{end.isoformat()}')"
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for table, _key in _PARTITIONED_TABLES:
        if not _table_exists(conn, table):
            continue
        if not _is_partitioned(conn, table):
            continue

        for offset in range(-_MONTHS_BACK, _MONTHS_FORWARD + 1):
            start = _add_months(anchor, offset)
            suffix = start.strftime("%Y_%m")
            partition_name = f"{table}_{suffix}"
            op.execute(sa.text(f"DROP TABLE IF EXISTS {partition_name}"))

        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}_default"))
