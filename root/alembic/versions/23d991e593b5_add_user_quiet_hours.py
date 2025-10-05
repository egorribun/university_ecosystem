"""add user quiet hours settings"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "23d991e593b5"
down_revision: Union[str, None] = "2bc18c38157c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "dnd_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.sql.expression.false(),
        ),
    )
    op.add_column("users", sa.Column("dnd_start", sa.Time(), nullable=True))
    op.add_column("users", sa.Column("dnd_end", sa.Time(), nullable=True))
    op.alter_column("users", "dnd_enabled", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "dnd_end")
    op.drop_column("users", "dnd_start")
    op.drop_column("users", "dnd_enabled")
