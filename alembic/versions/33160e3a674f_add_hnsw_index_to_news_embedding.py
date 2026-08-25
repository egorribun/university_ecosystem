"""add_hnsw_index_to_news_embedding

Revision ID: 33160e3a674f
Revises: 125613bc3543
Create Date: 2026-03-19 23:24:36.616935

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "33160e3a674f"  # pragma: allowlist secret
down_revision: str | None = "125613bc3543"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # op.execute("COMMIT")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS news_embedding_hnsw_idx "
            "ON news USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64);"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # op.execute("COMMIT")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS news_embedding_hnsw_idx;")
