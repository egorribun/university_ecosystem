from alembic import op

revision = "change_foreign_keys_ondelete"
down_revision = "7ea701e08870"
branch_labels = None
depends_on = None


def upgrade():
    # Удаляем старые ограничения
    op.drop_constraint("users_group_id_fkey", "users", type_="foreignkey")
    op.drop_constraint(
        "event_attendance_user_id_fkey", "event_attendance", type_="foreignkey"
    )
    op.drop_constraint(
        "event_attendance_event_id_fkey", "event_attendance", type_="foreignkey"
    )
    op.drop_constraint("events_created_by_fkey", "events", type_="foreignkey")
    op.drop_constraint("event_files_event_id_fkey", "event_files", type_="foreignkey")
    op.drop_constraint("news_author_id_fkey", "news", type_="foreignkey")
    op.drop_constraint(
        "invite_codes_used_by_user_id_fkey", "invite_codes", type_="foreignkey"
    )

    # Создаём новые с нужными ondelete
    op.create_foreign_key(
        "users_group_id_fkey",
        "users",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "event_attendance_user_id_fkey",
        "event_attendance",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "event_attendance_event_id_fkey",
        "event_attendance",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "events_created_by_fkey",
        "events",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "event_files_event_id_fkey",
        "event_files",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "news_author_id_fkey",
        "news",
        "users",
        ["author_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "invite_codes_used_by_user_id_fkey",
        "invite_codes",
        "users",
        ["used_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("users_group_id_fkey", "users", type_="foreignkey")
    op.drop_constraint(
        "event_attendance_user_id_fkey", "event_attendance", type_="foreignkey"
    )
    op.drop_constraint(
        "event_attendance_event_id_fkey", "event_attendance", type_="foreignkey"
    )
    op.drop_constraint("events_created_by_fkey", "events", type_="foreignkey")
    op.drop_constraint("event_files_event_id_fkey", "event_files", type_="foreignkey")
    op.drop_constraint("news_author_id_fkey", "news", type_="foreignkey")
    op.drop_constraint(
        "invite_codes_used_by_user_id_fkey", "invite_codes", type_="foreignkey"
    )

    # Восстановление без ondelete
    op.create_foreign_key(
        "users_group_id_fkey", "users", "groups", ["group_id"], ["id"]
    )
    op.create_foreign_key(
        "event_attendance_user_id_fkey",
        "event_attendance",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "event_attendance_event_id_fkey",
        "event_attendance",
        "events",
        ["event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "events_created_by_fkey", "events", "users", ["created_by"], ["id"]
    )
    op.create_foreign_key(
        "event_files_event_id_fkey", "event_files", "events", ["event_id"], ["id"]
    )
    op.create_foreign_key("news_author_id_fkey", "news", "users", ["author_id"], ["id"])
    op.create_foreign_key(
        "invite_codes_used_by_user_id_fkey",
        "invite_codes",
        "users",
        ["used_by_user_id"],
        ["id"],
    )
