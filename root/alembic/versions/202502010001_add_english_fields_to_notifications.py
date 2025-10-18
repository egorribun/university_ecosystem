"""Add English localization fields to notifications."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202502010001"
down_revision: Union[str, None] = "202501200001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply Add English localization fields to notifications."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("notifications")
    }

    with op.batch_alter_table("notifications") as batch_op:
        if "title_en" not in existing_columns:
            batch_op.add_column(sa.Column("title_en", sa.String(), nullable=True))
        if "body_en" not in existing_columns:
            batch_op.add_column(sa.Column("body_en", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    updated_columns = {
        column["name"] for column in inspector.get_columns("notifications")
    }

    if "title_en" in updated_columns:
        op.execute(
            sa.text(
                "UPDATE notifications SET title_en = title "
                "WHERE title IS NOT NULL AND (title_en IS NULL OR title_en = '')"
            )
        )
    if "body_en" in updated_columns:
        op.execute(
            sa.text(
                "UPDATE notifications SET body_en = body "
                "WHERE body IS NOT NULL AND (body_en IS NULL OR body_en = '')"
            )
        )


def downgrade() -> None:
    """Revert Add English localization fields to notifications."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("notifications")
    }

    with op.batch_alter_table("notifications") as batch_op:
        if "body_en" in existing_columns:
            batch_op.drop_column("body_en")
        if "title_en" in existing_columns:
            batch_op.drop_column("title_en")
