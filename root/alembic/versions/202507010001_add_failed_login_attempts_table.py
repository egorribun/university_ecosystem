from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "202507010001"
down_revision: Union[str, None] = "202506200001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failed_login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_failed_login_attempts_email",
        "failed_login_attempts",
        ["email"],
    )
    op.create_index(
        "ix_failed_login_attempts_attempted_at",
        "failed_login_attempts",
        ["attempted_at"],
    )
    op.create_index(
        "ix_failed_login_attempts_email_attempted_at",
        "failed_login_attempts",
        ["email", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_failed_login_attempts_email_attempted_at",
        table_name="failed_login_attempts",
    )
    op.drop_index(
        "ix_failed_login_attempts_attempted_at", table_name="failed_login_attempts"
    )
    op.drop_index("ix_failed_login_attempts_email", table_name="failed_login_attempts")
    op.drop_table("failed_login_attempts")
