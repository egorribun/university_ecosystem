"""Add keyset cursor index on news_comment for pagination.

AUDIT-BE-01 (audit 2026-03-15): The GET /{id}/interactions endpoint uses
OFFSET-based pagination on news_comment. An unbounded offset forces PostgreSQL
to scan and discard N rows before returning the result — O(N) sequential scan.

A composite index on (news_id, created_at ASC, id ASC) enables keyset cursor
pagination: the WHERE clause on the cursor tuple is satisfied by a B-tree seek
directly to the starting row, making page navigation O(log N) regardless of
page depth.

Created CONCURRENTLY to avoid table lock in production.

Revision ID: 202603150001
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "202603150001"
down_revision = "202603070001"
branch_labels = None
depends_on = None

_TABLE = "news_comments"
_IDX = "idx_news_comment_cursor"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Add keyset cursor composite index on news_comment."""
    if not _is_postgresql():
        # SQLite (test env) does not support CONCURRENTLY; add a plain index.
        op.create_index(_IDX, _TABLE, ["news_id", "created_at", "id"])
        return

    conn = op.get_bind()
    # CONCURRENTLY requires autocommit — commit any open transaction first.
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_IDX}
                ON {_TABLE} (news_id, created_at ASC, id ASC)
                """
            )
        )


def downgrade() -> None:
    """Drop the keyset cursor index."""
    if not _is_postgresql():
        op.drop_index(_IDX, table_name=_TABLE)
        return

    conn = op.get_bind()
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_IDX}"))
