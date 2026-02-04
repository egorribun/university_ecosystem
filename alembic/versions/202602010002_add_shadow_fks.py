"""Add shadow foreign key columns for migration phase 1

Revision ID: 202602010002
Revises: 202602010001
Create Date: 2026-02-01 04:30:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "202602010002"
down_revision = "202602010001"
branch_labels = None
depends_on = None
# (Table, Shadow Column Name)
FK_TABLES = [
    ("active_sessions", "shadow_user_id"),
    ("push_subscriptions", "shadow_user_id"),
    ("mfa_totp_enrollments", "shadow_user_id"),
    ("mfa_challenges", "shadow_user_id"),
    ("failed_login_attempts", "shadow_user_id"),
    ("password_reset_tokens", "shadow_user_id"),
    ("email_change_tokens", "shadow_user_id"),
    ("trusted_devices", "shadow_user_id"),
    ("webauthn_credentials", "shadow_user_id"),
    ("recovery_codes", "shadow_user_id"),
    ("login_history", "shadow_user_id"),
    ("event_attendance", "shadow_user_id"),
    ("event_attendance", "shadow_event_id"),
    ("event_files", "shadow_event_id"),
    ("news_likes", "shadow_user_id"),
    ("news_likes", "shadow_news_id"),
    ("news_comments", "shadow_user_id"),
    ("news_comments", "shadow_news_id"),
    ("events", "shadow_created_by"),
    ("invite_codes", "shadow_used_by_user_id"),
    ("chat_participants", "shadow_user_id"),
    ("messages", "shadow_sender_id"),
    ("spotify_integrations", "shadow_user_id"),
    ("stories", "shadow_user_id"),
    ("user_education_paths", "shadow_user_id"),
    ("user_preferences", "shadow_user_id"),
    ("user_profile_details", "shadow_user_id"),
    ("user_push_topics", "shadow_user_id"),
    ("users", "shadow_group_id"),
    ("schedule", "shadow_group_id"),
    ("news", "shadow_author_id"),
    ("notifications", "shadow_user_id"),
    ("notification_deliveries", "shadow_notification_id"),
    ("data_access_logs", "shadow_actor_user_id"),
    ("data_access_logs", "shadow_subject_user_id"),
    ("attachments", "shadow_message_id"),
    ("chat_participants", "shadow_chat_id"),
    ("messages", "shadow_chat_id"),
]


def upgrade():
    for table_name, col_name in FK_TABLES:
        op.add_column(
            table_name,
            sa.Column(col_name, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(f"ix_{table_name}_{col_name}", table_name, [col_name])


def downgrade():
    for table_name, col_name in FK_TABLES:
        try:
            op.drop_index(f"ix_{table_name}_{col_name}", table_name)
        except Exception:
            pass
        try:
            op.drop_column(table_name, col_name)
        except Exception:
            pass
