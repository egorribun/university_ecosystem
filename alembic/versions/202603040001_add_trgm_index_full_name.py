"""Add pg_trgm GIN index on user_profiles.full_name for ILIKE wildcard search.

PERF-03 (audit 2026-03-04): list_users() applies ``ILIKE '%text%'`` on
``UserProfile.full_name`` via a SQLAlchemy ``.ilike(f"%{term}%")`` expression.
The pre-existing B-tree index on ``lower(full_name)`` (text_pattern_ops) from
migration 202603030001 only helps anchored-prefix patterns like ``ILIKE 'text%'``.
It provides NO benefit for mid-string wildcards (``'%text%'``), so every fuzzy
name search still triggers a full sequential scan of user_profiles — O(N) in
user count.

The fix is a pg_trgm GIN index which decomposes the column into trigrams (3-char
sub-strings) and allows PostgreSQL to use the index for arbitrary ILIKE patterns
including ``'%text%'``.

References:
  - https://www.postgresql.org/docs/current/pgtrgm.html
  - OWASP Performance best practices for search endpoints

Revision ID: 202603040001
Revises: 202603030001
Create Date: 2026-03-04 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "202603040001"
down_revision: str | None = "202603030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GIN_INDEX_NAME = "ix_user_profiles_full_name_trgm"
_TABLE_NAME = "user_profiles"


def _is_postgresql() -> bool:
    """Return True when the live database dialect is PostgreSQL."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Create pg_trgm extension and GIN index for wildcard ILIKE search."""
    if not _is_postgresql():
        # SQLite (used in tests) does not support pg_trgm; skip silently.
        return

    conn = op.get_bind()
    # Enable the extension inside the transaction (allowed).
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    # CONCURRENTLY requires running outside an explicit transaction block.
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {_GIN_INDEX_NAME}
                ON {_TABLE_NAME}
                USING gin (full_name gin_trgm_ops)
                WHERE full_name IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    """Drop the GIN index (leave pg_trgm extension in place — shared resource)."""
    if not _is_postgresql():
        return

    conn = op.get_bind()
    # conn.execute(text("COMMIT"))
    with op.get_context().autocommit_block():
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_GIN_INDEX_NAME}"))
