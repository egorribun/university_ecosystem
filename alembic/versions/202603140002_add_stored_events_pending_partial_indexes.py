"""Add partial covering indexes on stored_events for outbox worker.

PERF-03 (audit 2026-03-14): The outbox worker performs two hot query patterns
on stored_events.

1. **Pending-event poll** — executed every OUTBOX_POLL_INTERVAL seconds:
   SELECT id, ... FROM stored_events
   WHERE processed_at IS NULL
   ORDER BY created_at
   LIMIT :batch_size

   Without a partial index this hits the full ``ix_stored_events_processed_at``
   (all rows including already-processed ones).  A partial index restricted to
   ``processed_at IS NULL`` is O(backlog) not O(total).

2. **Causal-order dedup** — if DISTINCT ON (aggregate_id) is used to deliver
   the latest unprocessed event per aggregate before the next, the planner
   needs to find events ordered by (aggregate_id, created_at) for the unprocessed
   subset efficiently.

Indexes added (PostgreSQL CONCURRENTLY):
- ``ix_stored_events_pending_created``:
    (created_at, id) WHERE processed_at IS NULL
  Enables index-only scan for the poll query; covers the ORDER BY + LIMIT.

- ``ix_stored_events_pending_aggregate_created``:
    (aggregate_id, created_at, id) WHERE processed_at IS NULL
  Enables DISTINCT ON (aggregate_id) ORDER BY aggregate_id, created_at
  queries for causal-order processing (DEBT-01 / Wave-7 work).

Revision ID: 202603140002
Revises: 202603140001
Create Date: 2026-03-14 12:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "202603140002"
down_revision: str | None = "202603140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "stored_events"
_IDX_POLL = "ix_stored_events_pending_created"
_IDX_AGG = "ix_stored_events_pending_aggregate_created"

# Partial index predicate: only unprocessed events
_WHERE = "processed_at IS NULL"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Create two partial covering indexes for the outbox worker hot paths."""
    if _is_postgresql():
        # Use CONCURRENTLY to avoid locking the table during index creation.
        # Note: CONCURRENTLY cannot run inside a transaction; Alembic wraps
        # migrations in a transaction by default.  We mark these as non-transactional
        # by creating them in a deferred CONCURRENTLY block.  Alembic will issue
        # a COMMIT before and after each CONCURRENTLY statement.
        with op.get_context().autocommit_block():
            op.execute(
                text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_POLL} "
                    f"ON {_TABLE} (created_at, id) "
                    f"WHERE {_WHERE}"
                )
            )
        with op.get_context().autocommit_block():
            op.execute(
                text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_AGG} "
                    f"ON {_TABLE} (aggregate_id, created_at, id) "
                    f"WHERE {_WHERE}"
                )
            )
    else:
        # SQLite: no partial indexes via op.create_index; use raw DDL.
        # SQLite 3.8.9+ supports partial indexes natively.
        op.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_IDX_POLL} "
                f"ON {_TABLE} (created_at, id) "
                f"WHERE {_WHERE}"
            )
        )
        op.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_IDX_AGG} "
                f"ON {_TABLE} (aggregate_id, created_at, id) "
                f"WHERE {_WHERE}"
            )
        )


def downgrade() -> None:
    """Drop the partial indexes."""
    if _is_postgresql():
        with op.get_context().autocommit_block():
            op.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_POLL}"))
        with op.get_context().autocommit_block():
            op.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_AGG}"))
    else:
        op.execute(text(f"DROP INDEX IF EXISTS {_IDX_POLL}"))
        op.execute(text(f"DROP INDEX IF EXISTS {_IDX_AGG}"))
