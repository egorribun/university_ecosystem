"""Drop the unused ``user_stats`` and ``vector_chunks`` tables.

``user_stats`` was a pre-aggregation cache that nothing ever wrote: attendance,
grades and participation statistics are computed from their source tables and
cached in Redis. ``vector_chunks`` backed an abandoned sharded-vector design;
semantic search reads the embedding stored on ``news`` rows instead. Neither
table has a reader or a writer in the application, so both are removed.

The downgrade recreates the empty tables (including the btree embedding index
the previous migrations created) so the revision stays reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "202610010001"
down_revision: str | None = "202609300002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_stats")
    op.execute("DROP TABLE IF EXISTS vector_chunks")


def downgrade() -> None:
    op.create_table(
        "user_stats",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attendance_percent", sa.Float(), server_default="0.0", nullable=False
        ),
        sa.Column(
            "attendance_present", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("attendance_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attendance_trend", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("grades_average", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("grades_trend", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "participation_events", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "participation_hours", sa.Float(), server_default="0.0", nullable=False
        ),
        sa.Column(
            "participation_groups", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "participation_trend", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "vector_chunks",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.String(length=256), nullable=True),
        sa.Column("document_id", sa.String(length=256), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_vector_chunks_chunk_index", ["chunk_index"]),
        ("ix_vector_chunks_course_id", ["course_id"]),
        ("ix_vector_chunks_created_at", ["created_at"]),
        ("ix_vector_chunks_document_id", ["document_id"]),
        ("ix_vector_chunks_embedding", ["embedding"]),
        ("ix_vector_chunks_is_active", ["is_active"]),
        ("ix_vector_chunks_tenant_course", ["tenant_id", "course_id"]),
        ("ix_vector_chunks_tenant_doc", ["tenant_id", "document_id"]),
        ("ix_vector_chunks_tenant_id", ["tenant_id"]),
    ):
        op.create_index(name, "vector_chunks", columns)
