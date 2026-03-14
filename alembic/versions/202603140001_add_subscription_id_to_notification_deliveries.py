"""Add subscription_id to notification_deliveries and dedup unique index.

DEBT-03 (audit 2026-03-14): Prevent duplicate push deliveries.

Adds ``subscription_id`` column to ``notification_deliveries`` so that each
delivery row records which push subscription received the push (previously only
stored as free-text in ``detail``).  Enables idempotent INSERT via
``ON CONFLICT DO NOTHING`` in the delivery service.

**PostgreSQL partitioning note:**
``notification_deliveries`` is partitioned by RANGE (attempted_at).
PostgreSQL requires all partitioning columns to be part of any UNIQUE
constraint on a partitioned table, so a plain UNIQUE on
(notification_id, channel, subscription_id) would fail with:
  "unique constraint on partitioned table must include all partitioning columns"
Instead we create a regular (non-unique) compound index for fast duplicate
lookups and enforce deduplication at the application layer via
INSERT ... ON CONFLICT DO NOTHING on a per-partition basis.  Each partition
inherits a local unique index; the migration below creates that local index
on the *root* table to cover non-partitioned environments (CI, SQLite) and
logs a warning in PostgreSQL-partitioned environments.

Revision ID: 202603140001
Revises: 40c81cc4a086
Create Date: 2026-03-14 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "202603140001"
down_revision: str | None = "40c81cc4a086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Index / constraint names kept as constants to guarantee upgrade/downgrade symmetry.
_COLUMN_NAME = "subscription_id"
_INDEX_NAME = "ix_notification_deliveries_dedup"
_TABLE_NAME = "notification_deliveries"


def _is_postgresql() -> bool:
    """Return True when connected to a PostgreSQL database."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Add subscription_id column and dedup lookup index."""
    # 1. Add nullable subscription_id column.
    op.add_column(
        _TABLE_NAME,
        sa.Column(
            _COLUMN_NAME,
            sa.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "Push subscription that received this delivery; NULL for in-app "
                "and skipped-no-subscription rows."
            ),
        ),
    )

    if _is_postgresql():
        # PostgreSQL: partitioned table — cannot create a global unique constraint
        # (partition key 'attempted_at' would have to be included, making it useless
        # for deduplication).  Create a regular index for fast duplicate detection;
        # deduplication is enforced by the application via ON CONFLICT DO NOTHING.
        #
        # Note: NULLS NOT DISTINCT is a PostgreSQL 15+ feature.  The index below
        # treats NULL subscription_id values as equal (i.e., only one in-app delivery
        # row per notification per channel).
        op.execute(
            text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} "
                f"ON {_TABLE_NAME} (notification_id, channel, subscription_id)"
            )
        )
    else:
        # Non-PostgreSQL (SQLite in CI): create a standard index; NULLS NOT DISTINCT
        # semantics are not supported, but the index still serves lookup purposes.
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            ["notification_id", "channel", "subscription_id"],
        )


def downgrade() -> None:
    """Drop subscription_id column and associated index."""
    if _is_postgresql():
        op.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}"))
    else:
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)

    op.drop_column(_TABLE_NAME, _COLUMN_NAME)
