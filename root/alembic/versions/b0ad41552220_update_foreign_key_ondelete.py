"""update foreign key ondelete"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b0ad41552220"
down_revision: Union[str, None] = "7ea701e08870"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _table_exists(table: str) -> bool:
    return table in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return any(col["name"] == column for col in _insp().get_columns(table))


def _drop_fk_by_columns(table: str, constrained_columns: list[str]) -> None:
    if not _table_exists(table):
        return
    inspector = _insp()
    target = set(constrained_columns)
    for fk in inspector.get_foreign_keys(table):
        cols = set(fk.get("constrained_columns") or [])
        name = fk.get("name")
        if cols == target and name:
            op.drop_constraint(name, table, type_="foreignkey")


def _create_fk(
    table: str,
    referred_table: str,
    constrained_columns: list[str],
    referred_columns: list[str],
    *,
    name: str,
    ondelete: Optional[str],
) -> None:
    if not (_table_exists(table) and _table_exists(referred_table)):
        return
    for column in constrained_columns:
        if not _column_exists(table, column):
            return
    op.create_foreign_key(
        name,
        table,
        referred_table,
        constrained_columns,
        referred_columns,
        ondelete=ondelete,
    )


def upgrade() -> None:
    if _is_sqlite():
        return

    _drop_fk_by_columns("users", ["group_id"])
    _drop_fk_by_columns("event_attendance", ["user_id"])
    _drop_fk_by_columns("event_attendance", ["event_id"])
    _drop_fk_by_columns("events", ["created_by"])
    _drop_fk_by_columns("event_files", ["event_id"])
    if _column_exists("news", "author_id"):
        _drop_fk_by_columns("news", ["author_id"])
    _drop_fk_by_columns("invite_codes", ["used_by_user_id"])

    _create_fk(
        "users",
        "groups",
        ["group_id"],
        ["id"],
        name=op.f("users_group_id_fkey"),
        ondelete="SET NULL",
    )
    _create_fk(
        "event_attendance",
        "users",
        ["user_id"],
        ["id"],
        name=op.f("event_attendance_user_id_fkey"),
        ondelete="CASCADE",
    )
    _create_fk(
        "event_attendance",
        "events",
        ["event_id"],
        ["id"],
        name=op.f("event_attendance_event_id_fkey"),
        ondelete="CASCADE",
    )
    _create_fk(
        "events",
        "users",
        ["created_by"],
        ["id"],
        name=op.f("events_created_by_fkey"),
        ondelete="SET NULL",
    )
    _create_fk(
        "event_files",
        "events",
        ["event_id"],
        ["id"],
        name=op.f("event_files_event_id_fkey"),
        ondelete="CASCADE",
    )
    if _column_exists("news", "author_id"):
        _create_fk(
            "news",
            "users",
            ["author_id"],
            ["id"],
            name=op.f("news_author_id_fkey"),
            ondelete="SET NULL",
        )
    _create_fk(
        "invite_codes",
        "users",
        ["used_by_user_id"],
        ["id"],
        name=op.f("invite_codes_used_by_user_id_fkey"),
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if _is_sqlite():
        return

    _drop_fk_by_columns("users", ["group_id"])
    _drop_fk_by_columns("event_attendance", ["user_id"])
    _drop_fk_by_columns("event_attendance", ["event_id"])
    _drop_fk_by_columns("events", ["created_by"])
    _drop_fk_by_columns("event_files", ["event_id"])
    if _column_exists("news", "author_id"):
        _drop_fk_by_columns("news", ["author_id"])
    _drop_fk_by_columns("invite_codes", ["used_by_user_id"])

    _create_fk(
        "users",
        "groups",
        ["group_id"],
        ["id"],
        name=op.f("users_group_id_fkey"),
        ondelete=None,
    )
    _create_fk(
        "event_attendance",
        "users",
        ["user_id"],
        ["id"],
        name=op.f("event_attendance_user_id_fkey"),
        ondelete=None,
    )
    _create_fk(
        "event_attendance",
        "events",
        ["event_id"],
        ["id"],
        name=op.f("event_attendance_event_id_fkey"),
        ondelete=None,
    )
    _create_fk(
        "events",
        "users",
        ["created_by"],
        ["id"],
        name=op.f("events_created_by_fkey"),
        ondelete="SET NULL",
    )
    _create_fk(
        "event_files",
        "events",
        ["event_id"],
        ["id"],
        name=op.f("event_files_event_id_fkey"),
        ondelete=None,
    )
    if _column_exists("news", "author_id"):
        _create_fk(
            "news",
            "users",
            ["author_id"],
            ["id"],
            name=op.f("news_author_id_fkey"),
            ondelete=None,
        )
    _create_fk(
        "invite_codes",
        "users",
        ["used_by_user_id"],
        ["id"],
        name=op.f("invite_codes_used_by_user_id_fkey"),
        ondelete=None,
    )
