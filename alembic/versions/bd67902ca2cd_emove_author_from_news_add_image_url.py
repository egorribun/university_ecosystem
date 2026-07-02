"""remove author from news, add image_url"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bd67902ca2cd"
down_revision: str | None = "b0ad41552220"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table: str) -> bool:
    return table in _insp().get_table_names()


def _get_fk_names(table: str, constrained_columns: list[str]) -> list[str]:
    if not _table_exists(table):
        return []
    inspector = _insp()
    target = set(constrained_columns)
    from typing import cast

    return [
        cast(str, fk["name"])
        for fk in inspector.get_foreign_keys(table)
        if fk.get("name") and set(fk.get("constrained_columns") or []) == target
    ]


def upgrade() -> None:
    if not _table_exists("news"):
        return

    fk_names = _get_fk_names("news", ["author_id"])
    columns = {column["name"] for column in _insp().get_columns("news")}

    with op.batch_alter_table("news") as batch_op:
        for fk_name in fk_names:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        if "author_id" in columns:
            batch_op.drop_index("ix_news_author_id")
            batch_op.drop_column("author_id")
        if "image_url" not in columns:
            batch_op.add_column(sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    if not _table_exists("news"):
        return

    fk_names = _get_fk_names("news", ["author_id"])
    columns = {column["name"] for column in _insp().get_columns("news")}

    with op.batch_alter_table("news") as batch_op:
        added_author = False
        if "author_id" not in columns:
            batch_op.add_column(sa.Column("author_id", sa.Integer(), nullable=True))
            added_author = True
        if not fk_names or added_author:
            batch_op.create_foreign_key(
                op.f("news_author_id_fkey"), "users", ["author_id"], ["id"]
            )
        if "image_url" in columns:
            batch_op.drop_column("image_url")
