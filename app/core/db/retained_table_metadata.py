"""Migration-owned schemas retained after their runtime models were retired.

Keep these definitions in Alembic's target metadata until a separately reviewed
maintenance migration removes the physical tables. They remain subject to normal
autogenerate drift checks; application metadata must not reclaim them implicitly.
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

RETAINED_TABLES = frozenset({"user_stats", "vector_chunks"})


def build_migration_metadata(runtime_metadata: sa.MetaData) -> sa.MetaData:
    """Copy active schemas and add the explicitly retained historical schemas."""
    conflicts = RETAINED_TABLES.intersection(runtime_metadata.tables)
    if conflicts:
        raise ValueError(
            f"Retained tables have competing runtime ownership: {sorted(conflicts)}"
        )
    metadata = sa.MetaData(naming_convention=runtime_metadata.naming_convention)
    for table in runtime_metadata.tables.values():
        table.to_metadata(metadata)
    _register_retained_tables(metadata)
    for name in RETAINED_TABLES:
        metadata.tables[name].info["retained_by_revision"] = "202610010001"
    return metadata


def _register_retained_tables(metadata: sa.MetaData) -> None:
    sa.Table(
        "user_stats",
        metadata,
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

    vector_chunks = sa.Table(
        "vector_chunks",
        metadata,
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
        sa.Index(name, *(vector_chunks.c[column] for column in columns))
