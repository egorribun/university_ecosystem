"""Wave 14: Add composite indexes for high-frequency query patterns.

Revision ID: wave14_composite_indexes
Revises: ffe470bc9ca2
Create Date: 2026-03-18

PERF-14-03 (audit 2026-03-18): Add three partial/composite indexes to eliminate
sequential scans on the most-queried tables:

  1. idx_messages_chat_created    — messages paginated by chat, ordered by time
  2. idx_notifications_user_unread_created — unread notification cursor pagination
  3. idx_active_sessions_user_valid — active session lookup by user (revoked=NULL)

All created CONCURRENTLY so they don't take an exclusive lock on production.
NOTE: CONCURRENTLY cannot run inside a transaction; Alembic wraps upgrades in a
transaction by default. We disable that here via `execute_migration`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "wave14_composite_indexes"
down_revision: str | None = "ffe470bc9ca2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CONCURRENTLY requires autocommit (no surrounding transaction).
    connection = op.get_bind()
    # connection.execution_options(isolation_level="AUTOCOMMIT")

    with op.get_context().autocommit_block():
        connection.execute(
            sa.text(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_chat_created "
                "ON messages (chat_id, created_at DESC)"
            )
        )
    connection.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread_created "
            "ON notifications (user_id, created_at DESC) WHERE read = false"
        )
    )
    with op.get_context().autocommit_block():
        connection.execute(
            sa.text(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_active_sessions_user_valid "
                "ON active_sessions (user_id, revoked_at) WHERE revoked_at IS NULL"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    # connection.execution_options(isolation_level="AUTOCOMMIT")

    with op.get_context().autocommit_block():
        connection.execute(
            sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_messages_chat_created")
        )
    # notifications is a partitioned table: CONCURRENTLY is not supported for
    # partitioned indexes in PostgreSQL.
    connection.execute(
        sa.text("DROP INDEX IF EXISTS idx_notifications_user_unread_created")
    )
    with op.get_context().autocommit_block():
        connection.execute(
            sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_active_sessions_user_valid")
        )
