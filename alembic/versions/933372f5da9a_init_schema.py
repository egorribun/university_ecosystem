"""init schema"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "933372f5da9a"
down_revision: str | None = "bd67902ca2cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def _has_index(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    inspector = _insp()
    has_index = getattr(inspector, "has_index", None)
    if callable(has_index):
        try:
            return bool(has_index(table, name))
        except (NotImplementedError, TypeError):
            pass
    return any(ix.get("name") == name for ix in inspector.get_indexes(table))


def _create_index_safe(
    name: str, table: str, columns: list[str], *, unique: bool = False, ops=op
) -> None:
    if not _table_exists(table) or _has_index(table, name):
        return
    try:
        ops.create_index(name, table, columns, unique=unique, if_not_exists=True)
    except TypeError:
        if not _has_index(table, name):
            ops.create_index(name, table, columns, unique=unique)


def _drop_index_safe(name: str, table: str, ops=op) -> None:
    if not _table_exists(table):
        return
    try:
        ops.drop_index(name, table_name=table, if_exists=True)
    except TypeError:
        if _has_index(table, name):
            ops.drop_index(name, table_name=table)


def _has_unique(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    inspector = _insp()
    return any(uc.get("name") == name for uc in inspector.get_unique_constraints(table))


def _drop_unique_safe(name: str, table: str, ops=op) -> None:
    if not _table_exists(table):
        return
    try:
        ops.drop_constraint(name, table, type_="unique", if_exists=True)
    except TypeError:
        if _has_unique(table, name):
            ops.drop_constraint(name, table, type_="unique")


def _create_unique_constraint_safe(
    name: str, table: str, columns: list[str], ops=op
) -> None:
    if not _table_exists(table) or _has_unique(table, name):
        return
    ops.create_unique_constraint(name, table, columns)


def _drop_fk_by_columns(table: str, constrained_columns: list[str], ops=op) -> None:
    if not _table_exists(table):
        return
    inspector = _insp()
    target = set(constrained_columns)
    for fk in inspector.get_foreign_keys(table):
        cols = set(fk.get("constrained_columns") or [])
        name = fk.get("name")
        if cols == target and name:
            ops.drop_constraint(name, table, type_="foreignkey")


def upgrade() -> None:
    # Create groups table if it doesn't exist (referenced by schedule)
    if not _table_exists("groups"):
        op.create_table(
            "groups",
            sa.Column("id", sa.VARCHAR(length=20), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        _create_index_safe(op.f("ix_groups_id"), "groups", ["id"], unique=False)
        _create_index_safe(op.f("ix_groups_name"), "groups", ["name"], unique=False)

    # Create users table if it doesn't exist
    if not _table_exists("users"):
        # Note: Enums are handled by helpers or we map to String/Enum.
        # UserRole enum: STUDENT, TEACHER, ADMIN, SUPERUSER

        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=True),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            # Use Native Enum for Postgres, String for SQLite
            # (handled by SQLAlchemy usually)
            sa.Column(
                "role",
                sa.Enum("STUDENT", "TEACHER", "ADMIN", "SUPERUSER", name="userrole"),
                nullable=False,
            ),
            # Fields added in 2bc18c38157c
            # (which runs before this but might have skipped)
            sa.Column("department", sa.String(), nullable=True),
            sa.Column("position", sa.String(), nullable=True),
            # Spotify fields referenced in this migration (if any) or existing by then
            sa.Column("spotify_access_token", sa.String(), nullable=True),
            sa.Column("spotify_refresh_token", sa.String(), nullable=True),
            sa.Column("spotify_token_expires_at", sa.DateTime(), nullable=True),
            sa.Column("spotify_scope", sa.String(), nullable=True),
            sa.Column("spotify_last_checked_at", sa.DateTime(), nullable=True),
            sa.Column("spotify_last_track_url", sa.String(), nullable=True),
            sa.Column("spotify_last_album_image_url", sa.String(), nullable=True),
            sa.Column("spotify_user_id", sa.String(), nullable=True),
            sa.Column("spotify_last_track_id", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        _create_index_safe(op.f("ix_users_email"), "users", ["email"], unique=True)
        _create_index_safe(op.f("ix_users_id"), "users", ["id"], unique=False)

    if _table_exists("event_attendance"):
        with op.batch_alter_table("event_attendance") as batch_op:
            if _column_exists("event_attendance", "user_id"):
                batch_op.alter_column(
                    "user_id",
                    existing_type=sa.INTEGER(),
                    nullable=False,
                )
            if _column_exists("event_attendance", "event_id"):
                batch_op.alter_column(
                    "event_id",
                    existing_type=sa.INTEGER(),
                    nullable=False,
                )
        _create_index_safe(
            op.f("ix_event_attendance_event_id"),
            "event_attendance",
            ["event_id"],
        )
        _create_index_safe(
            "ix_event_attendance_event_user",
            "event_attendance",
            ["event_id", "user_id"],
        )
        _create_index_safe(
            op.f("ix_event_attendance_registered_at"),
            "event_attendance",
            ["registered_at"],
        )
        _create_index_safe(
            op.f("ix_event_attendance_user_id"),
            "event_attendance",
            ["user_id"],
        )
        _create_unique_constraint_safe(
            "uq_event_attendance_user_event",
            "event_attendance",
            ["user_id", "event_id"],
        )

    if _table_exists("event_files"):
        with op.batch_alter_table("event_files") as batch_op:
            if _column_exists("event_files", "event_id"):
                batch_op.alter_column(
                    "event_id",
                    existing_type=sa.INTEGER(),
                    nullable=False,
                )
        _create_index_safe(
            op.f("ix_event_files_event_id"),
            "event_files",
            ["event_id"],
        )

    if _table_exists("events"):
        _create_index_safe(op.f("ix_events_created_at"), "events", ["created_at"])
        _create_index_safe(op.f("ix_events_ends_at"), "events", ["ends_at"])
        _create_index_safe(op.f("ix_events_event_type"), "events", ["event_type"])
        _create_index_safe(op.f("ix_events_is_active"), "events", ["is_active"])
        _create_index_safe(op.f("ix_events_starts_at"), "events", ["starts_at"])
        if _column_exists("events", "created_by") and _table_exists("users"):
            with op.batch_alter_table("events") as batch_op:
                _drop_fk_by_columns("events", ["created_by"], ops=batch_op)
                batch_op.create_foreign_key(
                    op.f("events_created_by_fkey"),
                    "users",
                    ["created_by"],
                    ["id"],
                    ondelete="CASCADE",
                )

    if _table_exists("groups"):
        _create_index_safe(op.f("ix_groups_name"), "groups", ["name"])

    if _table_exists("invite_codes"):
        with op.batch_alter_table("invite_codes") as batch_op:
            _drop_unique_safe(
                op.f("invite_codes_code_key"), "invite_codes", ops=batch_op
            )
            _create_index_safe(
                op.f("ix_invite_codes_code"),
                "invite_codes",
                ["code"],
                unique=True,
                ops=batch_op,
            )
        _create_index_safe(
            op.f("ix_invite_codes_created_at"),
            "invite_codes",
            ["created_at"],
        )
        _create_index_safe(
            op.f("ix_invite_codes_is_active"),
            "invite_codes",
            ["is_active"],
        )
        _create_index_safe(
            op.f("ix_invite_codes_is_used"),
            "invite_codes",
            ["is_used"],
        )

    if _table_exists("news"):
        _create_index_safe(op.f("ix_news_created_at"), "news", ["created_at"])

    if _table_exists("notifications"):
        if not _column_exists("notifications", "read_at"):
            op.add_column(
                "notifications",
                sa.Column("read_at", sa.DateTime(), nullable=True),
            )
        _create_index_safe(
            "ix_notifications_dupe_check",
            "notifications",
            ["user_id", "title", "url", "created_at"],
        )
        _create_index_safe(
            op.f("ix_notifications_read_at"),
            "notifications",
            ["read_at"],
        )
        _create_index_safe(
            "ix_notifications_user_created",
            "notifications",
            ["user_id", "created_at"],
        )

    if _table_exists("password_reset_tokens"):
        _create_index_safe(
            op.f("ix_password_reset_tokens_created_at"),
            "password_reset_tokens",
            ["created_at"],
        )
        _create_index_safe(
            op.f("ix_password_reset_tokens_used"),
            "password_reset_tokens",
            ["used"],
        )

    if _table_exists("schedule"):
        with op.batch_alter_table("schedule") as batch_op:
            if _column_exists("schedule", "group_id"):
                batch_op.alter_column(
                    "group_id",
                    existing_type=sa.INTEGER(),
                    nullable=False,
                )
            if _column_exists("schedule", "subject"):
                batch_op.alter_column(
                    "subject",
                    existing_type=sa.VARCHAR(),
                    nullable=False,
                )
            if _column_exists("schedule", "weekday"):
                batch_op.alter_column(
                    "weekday",
                    existing_type=sa.VARCHAR(),
                    nullable=False,
                )
            if _column_exists("schedule", "start_time"):
                batch_op.alter_column(
                    "start_time",
                    existing_type=postgresql.TIMESTAMP(),
                    nullable=False,
                )
            if _column_exists("schedule", "end_time"):
                batch_op.alter_column(
                    "end_time",
                    existing_type=postgresql.TIMESTAMP(),
                    nullable=False,
                )
        _create_index_safe(op.f("ix_schedule_end_time"), "schedule", ["end_time"])
        _create_index_safe(op.f("ix_schedule_group_id"), "schedule", ["group_id"])
        _create_index_safe(
            "ix_schedule_group_start_time",
            "schedule",
            ["group_id", "start_time"],
        )
        _create_index_safe(op.f("ix_schedule_parity"), "schedule", ["parity"])
        _create_index_safe(op.f("ix_schedule_start_time"), "schedule", ["start_time"])
        _create_index_safe(op.f("ix_schedule_weekday"), "schedule", ["weekday"])
        if _column_exists("schedule", "group_id") and _table_exists("groups"):
            with op.batch_alter_table("schedule") as batch_op:
                _drop_fk_by_columns("schedule", ["group_id"], ops=batch_op)
                batch_op.create_foreign_key(
                    op.f("schedule_group_id_fkey"),
                    "groups",
                    ["group_id"],
                    ["id"],
                    ondelete="CASCADE",
                )

    if _table_exists("users"):
        with op.batch_alter_table("users") as batch_op:
            if _column_exists("users", "spotify_access_token"):
                batch_op.alter_column(
                    "spotify_access_token",
                    existing_type=sa.TEXT(),
                    type_=sa.String(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_refresh_token"):
                batch_op.alter_column(
                    "spotify_refresh_token",
                    existing_type=sa.TEXT(),
                    type_=sa.String(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_token_expires_at"):
                batch_op.alter_column(
                    "spotify_token_expires_at",
                    existing_type=postgresql.TIMESTAMP(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_scope"):
                batch_op.alter_column(
                    "spotify_scope",
                    existing_type=sa.TEXT(),
                    type_=sa.String(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_last_checked_at"):
                batch_op.alter_column(
                    "spotify_last_checked_at",
                    existing_type=postgresql.TIMESTAMP(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_last_track_url"):
                batch_op.alter_column(
                    "spotify_last_track_url",
                    existing_type=sa.TEXT(),
                    type_=sa.String(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_last_album_image_url"):
                batch_op.alter_column(
                    "spotify_last_album_image_url",
                    existing_type=sa.TEXT(),
                    type_=sa.String(),
                    existing_nullable=True,
                )
            _drop_unique_safe(op.f("uq_users_spotify_user_id"), "users", ops=batch_op)
            _drop_index_safe(op.f("uq_users_spotify_user_id"), "users", ops=batch_op)
            _create_index_safe(
                op.f("ix_users_is_active"), "users", ["is_active"], ops=batch_op
            )
            _create_index_safe(op.f("ix_users_role"), "users", ["role"], ops=batch_op)
            _create_index_safe(
                op.f("ix_users_spotify_last_track_id"),
                "users",
                ["spotify_last_track_id"],
                ops=batch_op,
            )
            _create_index_safe(
                op.f("ix_users_spotify_token_expires_at"),
                "users",
                ["spotify_token_expires_at"],
                ops=batch_op,
            )
            _create_index_safe(
                op.f("ix_users_spotify_user_id"),
                "users",
                ["spotify_user_id"],
                unique=True,
                ops=batch_op,
            )


def downgrade() -> None:
    if _table_exists("users"):
        with op.batch_alter_table("users") as batch_op:
            _drop_index_safe(op.f("ix_users_spotify_user_id"), "users", ops=batch_op)
            _drop_index_safe(
                op.f("ix_users_spotify_token_expires_at"), "users", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_users_spotify_last_track_id"), "users", ops=batch_op
            )
            _drop_index_safe(op.f("ix_users_role"), "users", ops=batch_op)
            _drop_index_safe(op.f("ix_users_is_active"), "users", ops=batch_op)
            _create_index_safe(
                op.f("uq_users_spotify_user_id"),
                "users",
                ["spotify_user_id"],
                unique=True,
                ops=batch_op,
            )
            if _column_exists("users", "spotify_last_album_image_url"):
                batch_op.alter_column(
                    "spotify_last_album_image_url",
                    existing_type=sa.String(),
                    type_=sa.TEXT(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_last_track_url"):
                batch_op.alter_column(
                    "spotify_last_track_url",
                    existing_type=sa.String(),
                    type_=sa.TEXT(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_last_checked_at"):
                batch_op.alter_column(
                    "spotify_last_checked_at",
                    existing_type=sa.DateTime(),
                    type_=postgresql.TIMESTAMP(timezone=True),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_scope"):
                batch_op.alter_column(
                    "spotify_scope",
                    existing_type=sa.String(),
                    type_=sa.TEXT(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_token_expires_at"):
                batch_op.alter_column(
                    "spotify_token_expires_at",
                    existing_type=sa.DateTime(),
                    type_=postgresql.TIMESTAMP(timezone=True),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_refresh_token"):
                batch_op.alter_column(
                    "spotify_refresh_token",
                    existing_type=sa.String(),
                    type_=sa.TEXT(),
                    existing_nullable=True,
                )
            if _column_exists("users", "spotify_access_token"):
                batch_op.alter_column(
                    "spotify_access_token",
                    existing_type=sa.String(),
                    type_=sa.TEXT(),
                    existing_nullable=True,
                )

    if _table_exists("schedule"):
        with op.batch_alter_table("schedule") as batch_op:
            if _column_exists("schedule", "group_id") and _table_exists("groups"):
                _drop_fk_by_columns("schedule", ["group_id"], ops=batch_op)
                batch_op.create_foreign_key(
                    op.f("schedule_group_id_fkey"),
                    "groups",
                    ["group_id"],
                    ["id"],
                )
            _drop_index_safe(op.f("ix_schedule_weekday"), "schedule", ops=batch_op)
            _drop_index_safe(op.f("ix_schedule_start_time"), "schedule", ops=batch_op)
            _drop_index_safe(op.f("ix_schedule_parity"), "schedule", ops=batch_op)
            _drop_index_safe("ix_schedule_group_start_time", "schedule", ops=batch_op)
            _drop_index_safe(op.f("ix_schedule_group_id"), "schedule", ops=batch_op)
            _drop_index_safe(op.f("ix_schedule_end_time"), "schedule", ops=batch_op)
            if _column_exists("schedule", "end_time"):
                batch_op.alter_column(
                    "end_time",
                    existing_type=postgresql.TIMESTAMP(),
                    nullable=True,
                )
            if _column_exists("schedule", "start_time"):
                batch_op.alter_column(
                    "start_time",
                    existing_type=postgresql.TIMESTAMP(),
                    nullable=True,
                )
            if _column_exists("schedule", "weekday"):
                batch_op.alter_column(
                    "weekday",
                    existing_type=sa.VARCHAR(),
                    nullable=True,
                )
            if _column_exists("schedule", "subject"):
                batch_op.alter_column(
                    "subject",
                    existing_type=sa.VARCHAR(),
                    nullable=True,
                )
            if _column_exists("schedule", "group_id"):
                batch_op.alter_column(
                    "group_id",
                    existing_type=sa.INTEGER(),
                    nullable=True,
                )

    if _table_exists("invite_codes"):
        with op.batch_alter_table("invite_codes") as batch_op:
            _drop_index_safe(
                op.f("ix_invite_codes_is_used"), "invite_codes", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_invite_codes_is_active"), "invite_codes", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_invite_codes_created_at"), "invite_codes", ops=batch_op
            )
            _drop_index_safe(op.f("ix_invite_codes_code"), "invite_codes", ops=batch_op)
            _create_unique_constraint_safe(
                op.f("invite_codes_code_key"),
                "invite_codes",
                ["code"],
                ops=batch_op,
            )

    if _table_exists("events"):
        with op.batch_alter_table("events") as batch_op:
            if _column_exists("events", "created_by") and _table_exists("users"):
                _drop_fk_by_columns("events", ["created_by"], ops=batch_op)
                batch_op.create_foreign_key(
                    op.f("events_created_by_fkey"),
                    "users",
                    ["created_by"],
                    ["id"],
                    ondelete="SET NULL",
                )
            _drop_index_safe(op.f("ix_events_starts_at"), "events", ops=batch_op)
            _drop_index_safe(op.f("ix_events_is_active"), "events", ops=batch_op)
            _drop_index_safe(op.f("ix_events_event_type"), "events", ops=batch_op)
            _drop_index_safe(op.f("ix_events_ends_at"), "events", ops=batch_op)
            _drop_index_safe(op.f("ix_events_created_at"), "events", ops=batch_op)

    if _table_exists("password_reset_tokens"):
        with op.batch_alter_table("password_reset_tokens") as batch_op:
            _drop_index_safe(
                op.f("ix_password_reset_tokens_used"),
                "password_reset_tokens",
                ops=batch_op,
            )
            _drop_index_safe(
                op.f("ix_password_reset_tokens_created_at"),
                "password_reset_tokens",
                ops=batch_op,
            )

    if _table_exists("notifications"):
        with op.batch_alter_table("notifications") as batch_op:
            _drop_index_safe(
                "ix_notifications_user_created", "notifications", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_notifications_read_at"), "notifications", ops=batch_op
            )
            _drop_index_safe(
                "ix_notifications_dupe_check", "notifications", ops=batch_op
            )
            if _column_exists("notifications", "read_at"):
                batch_op.drop_column("read_at")

    if _table_exists("news"):
        with op.batch_alter_table("news") as batch_op:
            _drop_index_safe(op.f("ix_news_created_at"), "news", ops=batch_op)

    if _table_exists("groups"):
        with op.batch_alter_table("groups") as batch_op:
            _drop_index_safe(op.f("ix_groups_name"), "groups", ops=batch_op)

    if _table_exists("event_files"):
        with op.batch_alter_table("event_files") as batch_op:
            _drop_index_safe(
                op.f("ix_event_files_event_id"), "event_files", ops=batch_op
            )
            if _column_exists("event_files", "event_id"):
                batch_op.alter_column(
                    "event_id",
                    existing_type=sa.INTEGER(),
                    nullable=True,
                )

    if _table_exists("event_attendance"):
        with op.batch_alter_table("event_attendance") as batch_op:
            _drop_unique_safe(
                "uq_event_attendance_user_event", "event_attendance", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_event_attendance_user_id"), "event_attendance", ops=batch_op
            )
            _drop_index_safe(
                op.f("ix_event_attendance_registered_at"),
                "event_attendance",
                ops=batch_op,
            )
            _drop_index_safe(
                "ix_event_attendance_event_user",
                "event_attendance",
                ops=batch_op,
            )
            _drop_index_safe(
                op.f("ix_event_attendance_event_id"), "event_attendance", ops=batch_op
            )
            if _column_exists("event_attendance", "event_id"):
                batch_op.alter_column(
                    "event_id",
                    existing_type=sa.INTEGER(),
                    nullable=True,
                )
            if _column_exists("event_attendance", "user_id"):
                batch_op.alter_column(
                    "user_id",
                    existing_type=sa.INTEGER(),
                    nullable=True,
                )
