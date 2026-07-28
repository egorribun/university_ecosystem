"""Reconcile schema drift for grades table and tenant_id column cleanup.

Revision ID: 202607280001
Revises: 202607240001
Create Date: 2026-07-28 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202607280001"
down_revision: str | Sequence[str] | None = "202607240001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "grades" not in tables:
        op.create_table(
            "grades",
            sa.Column(
                "student_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False
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
                "assigned_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True
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
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grades CASCADE")
