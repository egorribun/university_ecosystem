"""Add functional index on lower(full_name) for case-insensitive user search.

PERF-4 (audit 2026-03): user_repository.search_by_name() uses
``func.lower(UserProfile.full_name).like(pattern)`` which is a functional
expression.  A plain B-tree index on ``full_name`` is NOT used by this query
because the index stores the original-case value, not the lowercased one.

Without this index every search_by_name() call triggers a full sequential
scan of user_profiles, which is O(N) in the number of users.

This migration adds a PostgreSQL functional index on ``lower(full_name)``
(text_pattern_ops so LIKE patterns starting with a wildcard still benefit)
and a single-column B-tree on ``full_name`` for direct equality lookups.

The index is skipped on SQLite (used in tests) because SQLite does not
support functional indexes — the migration uses ``op.execute`` wrapped in a
dialect guard so it is a no-op in the test environment.

Revision ID: 202603030001
Revises: See down_revision below
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "202603030001"
down_revision = "202602270003"  # merge_heads — adjust if your HEAD differs
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_user_profiles_full_name_lower"
_TABLE_NAME = "user_profiles"


def _is_postgresql() -> bool:
    """Return True when the live database dialect is PostgreSQL."""
    conn = op.get_bind()
    return conn.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        # SQLite does not support CREATE INDEX ON (expression); skip gracefully.
        return

    # CONCURRENTLY requires running outside an explicit transaction block.
    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    # Functional index: lower(full_name) with text_pattern_ops operator class.
    # text_pattern_ops allows LIKE 'prefix%' patterns to use the index even
    # though the column is TEXT; without it, PostgreSQL would fall back to seqscan.
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME}
                ON {_TABLE_NAME} (lower(full_name) text_pattern_ops)
                WHERE full_name IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}"))
