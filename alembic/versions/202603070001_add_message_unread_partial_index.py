"""Add partial index on message(chat_id, sender_id) WHERE read_status = FALSE.

TD-NEW-04 (audit 2026-03-07): The unread-count query executed by
``ChatRepository.get_unread_count`` and by the CTE in ``get_chats_for_user``
filters on three columns:

    WHERE chat_id = :chat_id
      AND sender_id != :user_id
      AND read_status = FALSE

Without a specialised index PostgreSQL must do a full or partial sequential
scan over ``message`` filtered to the given chat.  A partial index covering
only the rows where ``read_status = FALSE`` (which is typically a small
fraction of the total table) allows an Index Only Scan for these queries and
dramatically reduces I/O at the cost of a tiny index that shrinks
automatically as messages are marked read.

Index design:
  - (chat_id, sender_id) — covers the equality/inequality predicates in order
  - WHERE read_status = FALSE — partial: only unread messages are indexed

The index is created CONCURRENTLY so it does not lock the table on large
production deployments.  SQLite (used in unit tests) does not support
CONCURRENTLY or partial indexes; the upgrade/downgrade functions are no-ops
when not running against PostgreSQL.

Revision ID: 202603070001
Revises: 202603060001
Create Date: 2026-03-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "202603070001"
down_revision: str | None = "202603060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDX_UNREAD = "ix_messages_unread_chat_sender"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        # SQLite does not support CONCURRENTLY or partial indexes; skip in tests.
        return

    conn = op.get_bind()
    # CONCURRENTLY requires running outside an explicit transaction block.
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_UNREAD}
                ON messages (chat_id, sender_id)
                WHERE read_status = FALSE
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_UNREAD}"))
