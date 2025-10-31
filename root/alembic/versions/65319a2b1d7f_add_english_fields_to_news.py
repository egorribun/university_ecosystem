"""Add English localization fields to news."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "65319a2b1d7f"
down_revision: str | None = "2e93eecad1e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply Add English localization fields to news."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("news")}

    with op.batch_alter_table("news") as batch_op:
        if "title_en" not in existing_columns:
            batch_op.add_column(sa.Column("title_en", sa.String(), nullable=True))
        if "content_en" not in existing_columns:
            batch_op.add_column(sa.Column("content_en", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    updated_columns = {column["name"] for column in inspector.get_columns("news")}

    if "title_en" in updated_columns:
        op.execute(
            sa.text(
                "UPDATE news SET title_en = title "
                "WHERE title IS NOT NULL AND (title_en IS NULL OR title_en = '')"
            )
        )
    if "content_en" in updated_columns:
        op.execute(
            sa.text(
                "UPDATE news SET content_en = content "
                "WHERE content IS NOT NULL AND (content_en IS NULL OR content_en = '')"
            )
        )


def downgrade() -> None:
    """Revert Add English localization fields to news."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("news")}

    with op.batch_alter_table("news") as batch_op:
        if "content_en" in existing_columns:
            batch_op.drop_column("content_en")
        if "title_en" in existing_columns:
            batch_op.drop_column("title_en")
