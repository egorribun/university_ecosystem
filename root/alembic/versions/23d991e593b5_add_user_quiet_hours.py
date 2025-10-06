from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "23d991e593b5"
down_revision: Union[str, None] = "2bc18c38157c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {t for t in inspector.get_table_names()}
    if "users" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "dnd_enabled" not in columns:
        op.add_column("users", sa.Column("dnd_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "dnd_start" not in columns:
        op.add_column("users", sa.Column("dnd_start", sa.Time(), nullable=True))
    if "dnd_end" not in columns:
        op.add_column("users", sa.Column("dnd_end", sa.Time(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {t for t in inspector.get_table_names()}
    if "users" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "dnd_end" in columns:
        op.drop_column("users", "dnd_end")
    if "dnd_start" in columns:
        op.drop_column("users", "dnd_start")
    if "dnd_enabled" in columns:
        op.drop_column("users", "dnd_enabled")