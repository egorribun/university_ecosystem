"""Drop legacy INT columns after UUID migration

Revision ID: 202602010004
Revises: 202602010003
Create Date: 2026-02-01 06:00:00.000000

"""

import logging

from alembic import op

revision = "202602010004"
down_revision = "202602010003"

TABLES_TO_CLEANUP = [
    "users",
    "groups",
    "stored_events",
    "notification_queue_jobs",
    "push_subscriptions",
    "active_sessions",
    "mfa_totp_enrollments",
    "mfa_challenges",
    "failed_login_attempts",
    "password_reset_tokens",
    "email_change_tokens",
    "trusted_devices",
    "webauthn_credentials",
    "recovery_codes",
    "login_history",
    "events",
    "event_attendance",
    "event_files",
    "news",
    "news_likes",
    "news_comments",
    "invite_codes",
    "messages",
    "stories",
    "spotify_integrations",
    "user_education_paths",
    "user_preferences",
    "user_profile_details",
    "user_push_topics",
]

# (Table, Legacy FK Col)
FK_TO_CLEANUP = [
    ("active_sessions", "legacy_user_id"),
    ("chat_participants", "legacy_user_id"),
    ("email_change_tokens", "legacy_user_id"),
    ("event_attendance", "legacy_user_id"),
    ("failed_login_attempts", "legacy_user_id"),
    ("invite_codes", "legacy_used_by_user_id"),
    ("login_history", "legacy_user_id"),
    ("messages", "legacy_sender_id"),
    ("mfa_challenges", "legacy_user_id"),
    ("mfa_totp_enrollments", "legacy_user_id"),
    ("news_comments", "legacy_user_id"),
    ("news_likes", "legacy_user_id"),
    ("password_reset_tokens", "legacy_user_id"),
    ("push_subscriptions", "legacy_user_id"),
    ("recovery_codes", "legacy_user_id"),
    ("spotify_integrations", "legacy_user_id"),
    ("stories", "legacy_created_by"),
    ("trusted_devices", "legacy_user_id"),
    ("user_education_paths", "legacy_user_id"),
    ("user_preferences", "legacy_user_id"),
    ("user_profile_details", "legacy_user_id"),
    ("user_push_topics", "legacy_user_id"),
    ("webauthn_credentials", "legacy_user_id"),
    ("events", "legacy_created_by"),
    ("event_attendance", "legacy_event_id"),
    ("event_files", "legacy_event_id"),
    ("news_comments", "legacy_news_id"),
    ("news_likes", "legacy_news_id"),
    ("users", "legacy_group_id"),
    ("schedule", "legacy_group_id"),
    ("news", "legacy_author_id"),
]


def upgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Drop the legacy primary key columns and their unique constraints
    for table in TABLES_TO_CLEANUP:
        try:
            with op.batch_alter_table(table) as batch_op:
                # Drop the unique constraint we created in previous step
                if dialect != "sqlite":
                    batch_op.drop_constraint(f"uq_{table}_legacy_id", type_="unique")
                batch_op.drop_column("legacy_id")
            logger.info(f"Dropped legacy_id from {table}")
        except Exception as e:
            logger.warning(f"Could not drop legacy_id for {table}: {e}")
            try:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.alter_column("legacy_id", nullable=True)
            except Exception as e2:
                logger.error(f"Could not make legacy_id nullable for {table}: {e2}")

    # 2. Drop the legacy foreign key columns
    for table, legacy_col in FK_TO_CLEANUP:
        try:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column(legacy_col)
            logger.info(f"Dropped {legacy_col} from {table}")
        except Exception as e:
            logger.warning(f"Could not drop {legacy_col} for {table}: {e}")
            try:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.alter_column(legacy_col, nullable=True)
            except Exception as e2:
                logger.error(f"Could not make {legacy_col} nullable for {table}: {e2}")


def downgrade():
    # Adding columns back is complex because we've lost the data.
    # We would need to re-verify or restore from backup.
    # Leaving as pass for safety in this cutover phase.
    pass
