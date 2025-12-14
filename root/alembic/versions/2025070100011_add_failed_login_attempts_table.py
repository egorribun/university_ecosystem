from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

TABLE_NAME = "failed_login_attempts"
INDEX_DEFINITIONS = {
    "ix_failed_login_attempts_email": ["email"],
    "ix_failed_login_attempts_attempted_at": ["attempted_at"],
    "ix_failed_login_attempts_email_attempted_at": ["email", "attempted_at"],
}

revision: str = "2025070100011"
down_revision: str | None = "202506200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind is not None:
        inspector = sa.inspect(bind)
        if TABLE_NAME in inspector.get_table_names():
            existing_indexes = {
                index["name"] for index in inspector.get_indexes(TABLE_NAME)
            }
            for index_name, columns in INDEX_DEFINITIONS.items():
                if index_name not in existing_indexes:
                    op.create_index(index_name, TABLE_NAME, columns)
            return

    op.create_table(
        TABLE_NAME,
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
    for index_name, columns in INDEX_DEFINITIONS.items():
        op.create_index(index_name, TABLE_NAME, columns)


def downgrade() -> None:
    op.drop_index(
        "ix_failed_login_attempts_email_attempted_at",
        table_name=TABLE_NAME,
    )
    op.drop_index("ix_failed_login_attempts_attempted_at", table_name=TABLE_NAME)
    op.drop_index("ix_failed_login_attempts_email", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
