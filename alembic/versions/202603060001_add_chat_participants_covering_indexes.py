"""Add covering indexes on chat_participants for presence and unread-count queries.

PERF-02 (audit 2026-03-06): Two queries in chat_repository are doing Seq Scans
because the existing index only covers ``(chat_id)``:

1. ``get_presence_audience`` — resolves all peers of a user across their chats:
     SELECT DISTINCT user_id FROM chat_participants
     WHERE chat_id IN (SELECT chat_id FROM chat_participants WHERE user_id = ?)
     LIMIT 500
   Requires an Index Only Scan on ``(chat_id, user_id)``.

2. ``get_chats_for_user`` + related presence lookups — fetches chats a user
   belongs to:
     SELECT chat_id FROM chat_participants WHERE user_id = ?
   Requires an index with ``user_id`` as the leading column.

Both queries can become Index Only Scans (zero heap access) once the
appropriate covering indexes exist.

Revision ID: 202603060001
Revises: 202603040001
Create Date: 2026-03-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "202603060001"
down_revision: str | None = "202603040001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Index names follow ix_<table>_<columns> convention.
_IDX_USER_CHAT = "ix_chat_participants_user_id_chat_id"
_IDX_CHAT_USER = "ix_chat_participants_chat_id_user_id"
_TABLE = "chat_participants"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Add two CONCURRENTLY-built covering indexes on chat_participants."""
    if not _is_postgresql():
        # SQLite used in unit tests does not support CONCURRENTLY; skip.
        return

    conn = op.get_bind()
    # CONCURRENTLY requires running outside an explicit transaction block.
    # conn.execute(text("COMMIT"))

    # Index 1: user_id → chat_id covering index.
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_USER_CHAT}
                ON {_TABLE} (user_id, chat_id)
                """
            )
        )

    # Index 2: chat_id → user_id covering index.
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX_CHAT_USER}
                ON {_TABLE} (chat_id, user_id)
                """
            )
        )


def downgrade() -> None:
    """Drop the two covering indexes."""
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_USER_CHAT}"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX_CHAT_USER}"))
