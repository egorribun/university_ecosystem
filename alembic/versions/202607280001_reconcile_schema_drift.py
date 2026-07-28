"""Reconcile schema drift for grades, tenants, vector_chunks tables and tenant_id column cleanup.

Revision ID: 202607280001
Revises: 202607240001
Create Date: 2026-07-28 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "202607280001"
down_revision: str | Sequence[str] | None = "202607240001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("domain", sa.String(length=256), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        )
        op.create_index("ix_tenants_domain", "tenants", ["domain"], unique=True)
        op.create_index("ix_tenants_is_active", "tenants", ["is_active"])
        op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    if "vector_chunks" not in tables:
        op.create_table(
            "vector_chunks",
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("course_id", sa.String(length=256), nullable=True),
            sa.Column("document_id", sa.String(length=256), nullable=False),
            sa.Column(
                "chunk_index",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("embedding", Vector(1536), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        )
        op.create_index(
            "ix_vector_chunks_chunk_index", "vector_chunks", ["chunk_index"]
        )
        op.create_index("ix_vector_chunks_course_id", "vector_chunks", ["course_id"])
        op.create_index("ix_vector_chunks_created_at", "vector_chunks", ["created_at"])
        op.create_index(
            "ix_vector_chunks_document_id", "vector_chunks", ["document_id"]
        )
        op.create_index("ix_vector_chunks_embedding", "vector_chunks", ["embedding"])
        op.create_index("ix_vector_chunks_is_active", "vector_chunks", ["is_active"])
        op.create_index(
            "ix_vector_chunks_tenant_course",
            "vector_chunks",
            ["tenant_id", "course_id"],
        )
        op.create_index(
            "ix_vector_chunks_tenant_doc",
            "vector_chunks",
            ["tenant_id", "document_id"],
        )
        op.create_index("ix_vector_chunks_tenant_id", "vector_chunks", ["tenant_id"])

    if "grades" not in tables:
        op.create_table(
            "grades",
            sa.Column(
                "student_id",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("subject", sa.String(length=100), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column(
                "assessment_type",
                sa.String(length=50),
                nullable=False,
                server_default="exam",
            ),
            sa.Column(
                "assigned_by",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        )
        op.create_index("ix_grades_student_id", "grades", ["student_id"])
        op.create_index(
            "ix_grades_student_subject", "grades", ["student_id", "subject"]
        )
        op.create_index("ix_grades_subject", "grades", ["subject"])

    op.execute("ALTER TABLE chats DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE groups DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE news DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tenant_id CASCADE")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grades CASCADE")
    op.execute("DROP TABLE IF EXISTS vector_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")
