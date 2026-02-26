"""Add partial covering index on active_sessions (PERF-4: audit 2026-02-26).

Problem
-------
get_active_sessions_for_user and _enforce_concurrent_limit both execute:

    SELECT ... FROM active_sessions
    WHERE user_id = $1
      AND revoked_at IS NULL
    ORDER BY created_at DESC

Without a covering index, PostgreSQL uses a seq-scan (or at best a plain
btree index on user_id) followed by a heap filter on revoked_at.  For users
with 100+ historical sessions this degrades to O(N) per auth request.

Fix
---
A partial index that covers (user_id, created_at) WHERE revoked_at IS NULL
lets PostgreSQL resolve the query with an index-only scan on the subset of
non-revoked rows — O(log M) where M << N.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202602260001"
down_revision = "202602040002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial index: covers only non-revoked sessions (the hot path).
    # PostgreSQL will use this for the WHERE user_id=$1 AND revoked_at IS NULL
    # clause without a heap re-check on the revoked_at filter.
    op.create_index(
        "ix_active_sessions_user_active_created",
        "active_sessions",
        ["user_id", "created_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_active_sessions_user_active_created",
        table_name="active_sessions",
    )
