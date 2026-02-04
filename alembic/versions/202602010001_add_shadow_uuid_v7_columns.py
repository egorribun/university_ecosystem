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
    "chat_participants",
    "messages",
    "spotify_integrations",
    "stories",
    "user_education_paths",
    "user_preferences",
    "user_profile_details",
    "user_push_topics",
]


def upgrade():
    for table_name in TABLES:
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
        op.create_index(
            f"ix_{table_name}_uuid_id", table_name, ["uuid_id"], unique=True
        )


def downgrade():
    for table_name in TABLES:
        idx_name = f"ix_{table_name}_uuid_id"
        op.drop_index(idx_name, table_name)
        op.drop_column(table_name, "uuid_id")
