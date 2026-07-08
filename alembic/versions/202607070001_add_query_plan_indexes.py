"""Add indexes required for EXPLAIN ANALYZE query plan gate.

WHY (W25 query-plan gate): three critical queries run on every page load
and every authenticated request.  Without composite indexes the planner
falls back to sequential scans, which break P99 SLOs at scale:

  1. events_by_date   — filters on (start_time, is_published)
  2. user_sessions    — filters on (user_id, expires_at)
  3. notifications_unread — filters on (user_id, is_read)

See tests/test_query_plans.py for the corresponding EXPLAIN ANALYZE gate.

Revision ID: a3f8c1d2e047
Revises: 202607020001
Create Date: 2026-07-07
"""

from alembic import op

revision = "a3f8c1d2e047"  # pragma: allowlist secret
down_revision = "202607020001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Index for events_by_date query (test_events_by_date_no_seq_scan)
    op.create_index(
        "ix_events_starts_at_is_active",
        "events",
        ["starts_at", "is_active"],
        unique=False,
    )
    # Index for user_sessions query (test_user_sessions_no_seq_scan)
    op.create_index(
        "ix_active_sessions_user_id_expires_at",
        "active_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )
    # Index for notifications_unread query (test_notifications_unread_count_no_seq_scan)
    op.create_index(
        "ix_notifications_user_id_read",
        "notifications",
        ["user_id", "read"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id_read", table_name="notifications")
    op.drop_index("ix_active_sessions_user_id_expires_at", table_name="active_sessions")
    op.drop_index("ix_events_starts_at_is_active", table_name="events")
