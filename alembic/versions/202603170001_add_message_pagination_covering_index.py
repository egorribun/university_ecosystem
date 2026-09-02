"""Replace pagination index with a covering index (INCLUDE clause).

PERF-W10-01 (audit 2026-03-17): The previous index (202603160001) was created
on table ``message`` but the ORM table is ``messages``.  Additionally, the
original index does not include ``sender_id`` and ``read_status`` — columns
that are fetched on every message-list response.  Without INCLUDE, PostgreSQL
performs a heap fetch per row even when the index fully satisfies the WHERE /
ORDER BY predicates (i.e. no Index-Only Scan is possible).

This migration:
  1. Drops the wrongly-named index (if it exists) from the earlier migration.
  2. Drops the old index on ``messages`` if it somehow exists.
  3. Creates a new covering index on ``messages`` (correct table name) with
     an INCLUDE clause covering the two small fixed-size columns:
       - sender_id   — always fetched, 16-byte UUID
       - read_status — always fetched, 1-byte boolean
     ``content`` is intentionally excluded from INCLUDE — it is TEXT (up to
     10 000 chars after RZ-W10-10) and including it would inflate the index
     by several gigabytes on a busy chat table.

Revision ID: 202603170001
Revises: 202603160001
Create Date: 2026-03-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "202603170001"
down_revision: str | None = "202603160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The previous migration accidentally referenced the wrong table name ("message"
# instead of "messages").  We clean it up here in case it was applied.
_OLD_IDX_WRONG_TABLE = "idx_message_chat_pagination"  # on table "message" (wrong)
_OLD_IDX_CORRECT_TABLE = (
    "idx_message_chat_pagination"  # on table "messages" (if it ever existed)
)
_NEW_IDX = "idx_messages_chat_pagination_covering"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))

    # Drop legacy index from the previous migration (wrong table "message").
    # IF NOT EXISTS / IF EXISTS guard makes this idempotent.
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_OLD_IDX_WRONG_TABLE}"))

    # Create the new covering index on the correct table "messages".
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_NEW_IDX}
                ON messages (chat_id, created_at DESC, id DESC)
                INCLUDE (sender_id, read_status)
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_NEW_IDX}"))

    # Restore the original index (correct table name, no INCLUDE).
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_OLD_IDX_WRONG_TABLE}
                ON messages (chat_id, created_at DESC, id DESC)
                """
            )
        )
