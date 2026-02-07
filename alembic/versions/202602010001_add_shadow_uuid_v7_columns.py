"""Add shadow UUID v7 columns for migration phase 1

Revision ID: 202602010001
Revises: 202601260001
Create Date: 2026-02-01 04:15:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "202602010001"
down_revision = "202601260001"
branch_labels = None
depends_on = None

TABLES = [
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
    "login_history",
    "events",
    "event_attendance",
    "event_files",
    "news",
    "news_likes",
    "news_comments",
    "invite_codes",
    "chat_participants",
    "messages",
    "spotify_integrations",
    "stories",
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


PARTITION_KEYS = {
    "notifications": "created_at",
    "notification_deliveries": "attempted_at",
    "data_access_logs": "created_at",
}


def upgrade():
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    inspector = sa.inspect(bind)

    for table_name in TABLES:
        existing_cols = {c["name"]: c for c in inspector.get_columns(table_name)}

        # Check if already migrated (id is UUID)
        id_col = existing_cols.get("id")
        if id_col and isinstance(id_col["type"], postgresql.UUID):
            continue

        if "uuid_id" not in existing_cols:
            op.add_column(
                table_name,
                sa.Column(
                    "uuid_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )

        # Create an index explicitly since index=True might not be
        # enough for some dialects
        cols = ["uuid_id"]
        if is_postgresql and table_name in PARTITION_KEYS:
            cols.append(PARTITION_KEYS[table_name])

        idx_name = f"ix_{table_name}_uuid_id"
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if idx_name not in existing_indexes:
            op.create_index(idx_name, table_name, cols, unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in TABLES:
        # Check if table still exists (might have been dropped in earlier steps)
        if table_name not in inspector.get_table_names():
            continue

        # On PostgreSQL, a UNIQUE index created with unique=True
        # also creates a UNIQUE CONSTRAINT with the same name.
        existing_constraints = {
            c["name"] for c in inspector.get_unique_constraints(table_name)
        }
        idx_name = f"ix_{table_name}_uuid_id"

        if idx_name in existing_constraints:
            op.drop_constraint(idx_name, table_name, type_="unique")

        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name)

        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        if "uuid_id" in existing_cols:
            op.drop_column(table_name, "uuid_id")
