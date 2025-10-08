"""remove author from news, add image_url

Revision ID: bd67902ca2cd
Revises: change_foreign_keys_ondelete
Create Date: 2025-06-14 06:36:56.799150

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd67902ca2cd"
down_revision: str | None = "change_foreign_keys_ondelete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "news" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("news")}
    fkeys = {fk["name"] for fk in inspector.get_foreign_keys("news") if fk.get("name")}
    with op.batch_alter_table("news") as batch_op:
        if "news_author_id_fkey" in fkeys:
            batch_op.drop_constraint("news_author_id_fkey", type_="foreignkey")
        if "author_id" in columns:
            batch_op.drop_column("author_id")
        if "image_url" not in columns:
            batch_op.add_column(sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "news" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("news")}
    fkeys = {fk["name"] for fk in inspector.get_foreign_keys("news") if fk.get("name")}
    with op.batch_alter_table("news") as batch_op:
        if "author_id" not in columns:
            batch_op.add_column(sa.Column("author_id", sa.Integer(), nullable=True))
        if "news_author_id_fkey" not in fkeys:
            batch_op.create_foreign_key(
                "news_author_id_fkey", "users", ["author_id"], ["id"]
            )
        if "image_url" in columns:
            batch_op.drop_column("image_url")
