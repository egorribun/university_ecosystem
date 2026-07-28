"""Drop legacy INT columns after UUID migration

Revision ID: 202602010004
Revises: 202602010003
Create Date: 2026-02-01 06:00:00.000000

"""

import contextlib
import logging

import sqlalchemy as sa

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
    "chats",
    "attachments",
    "notifications",
    "notification_deliveries",
    "data_access_logs",
    "schedule",
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
    ("notifications", "legacy_user_id"),
    ("notification_deliveries", "legacy_notification_id"),
    ("data_access_logs", "legacy_actor_user_id"),
    ("data_access_logs", "legacy_subject_user_id"),
    ("attachments", "legacy_message_id"),
    ("chat_participants", "legacy_chat_id"),
    ("messages", "legacy_chat_id"),
]


def upgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    dialect = bind.dialect.name

    # We do NOT use inspector here because heavy DDL in previous steps
    # causes asyncpg generic cache to fail with "pg_namespace.nspname != $7"
    # referencing stale types/tables when inspecting.
    # Instead, we just try to drop the columns and ignore missing errors.

    # 1. Drop the legacy primary key columns and their unique constraints
    for table in TABLES_TO_CLEANUP:
        if not sa.inspect(op.get_bind()).has_table(table):
            logger.info(f"Skipping drop for missing table {table}")
            continue

        print(f"Cleaning legacy_id {table}...")
        try:
            if dialect == "postgresql":
                # Drop constraint if exists (CASCADE handles it usually)
                if table == "active_sessions":
                    op.execute(  # nosemgrep
                        f'ALTER TABLE "{table}" '
                        f'DROP CONSTRAINT IF EXISTS "uq_{table}_legacy_id" CASCADE'
                    )

                op.execute(  # nosemgrep
                    f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "legacy_id" CASCADE'
                )
                logger.info(f"Dropped legacy_id from {table} (Postgres)")
            else:
                with op.batch_alter_table(table) as batch_op:
                    if dialect != "sqlite":
                        with contextlib.suppress(Exception):
                            batch_op.drop_constraint(
                                f"uq_{table}_legacy_id", type_="unique"
                            )
                    batch_op.drop_column("legacy_id")
                logger.info(f"Dropped legacy_id from {table}")
        except Exception as e:
            logger.info(f"Skipping legacy_id drop for {table}: {e}")

    # 2. Drop the legacy foreign key columns
    for table, legacy_col in FK_TO_CLEANUP:
        if not sa.inspect(op.get_bind()).has_table(table):
            continue

        print(f"Cleaning FK {legacy_col} in {table}...")
        try:
            if dialect == "postgresql":
                op.execute(  # nosemgrep
                    f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS '
                    f'"{legacy_col}" CASCADE'
                )
                logger.info(f"Dropped {legacy_col} from {table} (Postgres)")
            else:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.drop_column(legacy_col)
                logger.info(f"Dropped {legacy_col} from {table}")
        except Exception as e:
            logger.info(f"Skipping {legacy_col} drop for {table}: {e}")


def downgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Restore legacy columns as nullable to avoid errors in previous downgrades.
    # Note: Data loss for these columns is expected after upgrade.
    inspector = sa.inspect(bind)
    for table in TABLES_TO_CLEANUP:
        if not inspector.has_table(table):
            continue
        # Use String for tables known to have String IDs, default to Integer
        col_type_str = (
            "VARCHAR" if table in ("chats", "messages", "attachments") else "INTEGER"
        )
        if dialect == "postgresql":
            op.execute(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                f'"legacy_id" {col_type_str}'
            )
        else:
            try:
                with op.batch_alter_table(table) as batch_op:
                    col_type = (
                        sa.String()
                        if table in ("chats", "messages", "attachments")
                        else sa.Integer()
                    )
                    batch_op.add_column(sa.Column("legacy_id", col_type, nullable=True))
            except Exception as e:
                logger.warning(f"Could not restore legacy_id for {table}: {e}")

    for table, legacy_col in FK_TO_CLEANUP:
        if not inspector.has_table(table):
            continue
        col_type_str = (
            "VARCHAR"
            if "chat_id" in legacy_col or "message_id" in legacy_col
            else "INTEGER"
        )
        if dialect == "postgresql":
            op.execute(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                f'"{legacy_col}" {col_type_str}'
            )
        else:
            try:
                with op.batch_alter_table(table) as batch_op:
                    col_type = (
                        sa.String()
                        if "chat_id" in legacy_col or "message_id" in legacy_col
                        else sa.Integer()
                    )
                    batch_op.add_column(sa.Column(legacy_col, col_type, nullable=True))
            except Exception as e:
                logger.warning(f"Could not restore {legacy_col} for {table}: {e}")
