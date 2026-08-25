"""Add composite index for message pagination by chat.

PERF-W9-04 (audit 2026-03-16): The typical message-list query is:

    SELECT * FROM message
    WHERE chat_id = :chat_id
    ORDER BY created_at DESC, id DESC
    LIMIT 50

Without a composite index PostgreSQL falls back to a sequential scan of all
messages in the chat, which degrades from O(log N) to O(N) as chat history
grows.  A covering index on (chat_id, created_at DESC, id DESC) enables an
Index Scan that returns rows in the correct order with no sort step.

This also supports keyset ("cursor") pagination:

    WHERE chat_id = :chat_id
      AND (created_at, id) < (:last_created_at, :last_id)
    ORDER BY created_at DESC, id DESC
    LIMIT 50

Index design:
  - chat_id      — high-selectivity equality prefix
  - created_at DESC — matches ORDER BY / keyset inequality direction
  - id DESC      — tie-breaker; also used as the cursor key

The index is created CONCURRENTLY so it does not acquire an exclusive lock
on large production tables.  SQLite (used in unit tests) does not support
CONCURRENTLY; the upgrade/downgrade functions are no-ops when not running
against PostgreSQL.

Revision ID: 202603160001
Revises: 202603150002
Create Date: 2026-03-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "202603160001"
down_revision: str | None = "202603150002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDX_MSG_PAGINATION = "idx_message_chat_pagination"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        # SQLite does not support CONCURRENTLY; skip in unit-test environments.
        return

    conn = op.get_bind()
    # CONCURRENTLY requires running outside an explicit transaction block.
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_MSG_PAGINATION}
                ON messages (chat_id, created_at DESC, id DESC)
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    conn = op.get_bind()
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_MSG_PAGINATION}"))
