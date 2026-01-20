"""create_dead_letter_jobs_table

Revision ID: 3081a2b724cc
Revises: 2956fd6376cc
Create Date: 2026-01-19 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "3081a2b724cc"
down_revision = "2956fd6376cc"
branch_labels = None
depends_on = None


def upgrade():
    # Create dead_letter_jobs table
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("dead_letter_jobs"):
        op.create_table(
            "dead_letter_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_type", sa.String(length=100), nullable=False),
            sa.Column("job_hash", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
            sa.Column(
                "status", sa.String(length=20), server_default="pending", nullable=False
            ),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_hash"),
        )

    # Create indexes
    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("dead_letter_jobs")}
        if inspector.has_table("dead_letter_jobs")
        else set()
    )

    if op.f("ix_dead_letter_jobs_job_type") not in existing_indexes:
        op.create_index(
            op.f("ix_dead_letter_jobs_job_type"),
            "dead_letter_jobs",
            ["job_type"],
            unique=False,
        )
    if op.f("ix_dead_letter_jobs_status") not in existing_indexes:
        op.create_index(
            op.f("ix_dead_letter_jobs_status"),
            "dead_letter_jobs",
            ["status"],
            unique=False,
        )
    if op.f("ix_dead_letter_jobs_next_retry_at") not in existing_indexes:
        op.create_index(
            op.f("ix_dead_letter_jobs_next_retry_at"),
            "dead_letter_jobs",
            ["next_retry_at"],
            unique=False,
        )

    # Composite index from __table_args__
    if "ix_dlq_status_next_retry" not in existing_indexes:
        op.create_index(
            "ix_dlq_status_next_retry",
            "dead_letter_jobs",
            ["status", "next_retry_at"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("dead_letter_jobs"):
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("dead_letter_jobs")
        }

        if "ix_dlq_status_next_retry" in existing_indexes:
            op.drop_index("ix_dlq_status_next_retry", table_name="dead_letter_jobs")
        if op.f("ix_dead_letter_jobs_next_retry_at") in existing_indexes:
            op.drop_index(
                op.f("ix_dead_letter_jobs_next_retry_at"), table_name="dead_letter_jobs"
            )
        if op.f("ix_dead_letter_jobs_status") in existing_indexes:
            op.drop_index(
                op.f("ix_dead_letter_jobs_status"), table_name="dead_letter_jobs"
            )
        if op.f("ix_dead_letter_jobs_job_type") in existing_indexes:
            op.drop_index(
                op.f("ix_dead_letter_jobs_job_type"), table_name="dead_letter_jobs"
            )
        op.drop_table("dead_letter_jobs")
