from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202506200001"
down_revision: Union[str, None] = "202506150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_en", sa.String(), nullable=True),
        sa.Column("short_text", sa.Text(), nullable=False),
        sa.Column("short_text_en", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
        sa.Column("cta_url", sa.String(), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_stories_created_by_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_stories_expires_at_is_active",
        "stories",
        ["expires_at", "is_active"],
    )
    op.create_index("ix_stories_is_active", "stories", ["is_active"])
    op.create_index("ix_stories_created_by", "stories", ["created_by"])
    op.create_index("ix_stories_created_at", "stories", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_stories_created_at", table_name="stories")
    op.drop_index("ix_stories_created_by", table_name="stories")
    op.drop_index("ix_stories_is_active", table_name="stories")
    op.drop_index("ix_stories_expires_at_is_active", table_name="stories")
    op.drop_table("stories")
