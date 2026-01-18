"""Add additional performance indexes for notifications and sessions.

These indexes improve query performance for:
1. Notification retrieval with ordering
2. Active session presence lookups
3. Push subscription topic filtering

Revision ID: 202601130001
Revises: ede66395ff71_merge_chat_message_index_and_
Create Date: 2026-01-13 19:15:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202601130001"
down_revision = "ede66395ff71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()

    # Notifications: Composite index for user's notification feed
    # Optimizes: SELECT * FROM notifications WHERE user_id = ?
    #            ORDER BY created_at DESC LIMIT ?
    if "notifications" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("notifications")
        }

        if "ix_notifications_user_created_desc" not in existing_indexes:
            op.create_index(
                "ix_notifications_user_created_desc",
                "notifications",
                ["user_id", sa.text("created_at DESC")],
                unique=False,
                postgresql_using="btree",
            )

        # Index for unread notifications count
        if "ix_notifications_user_unread" not in existing_indexes:
            op.create_index(
                "ix_notifications_user_unread",
                "notifications",
                ["user_id", "read"],
                unique=False,
            )

    # Active Sessions: Index for presence map building
    # Optimizes: SELECT user_id, MAX(last_seen_at) FROM active_sessions
    #            WHERE user_id IN (...) GROUP BY user_id
    if "active_sessions" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("active_sessions")
        }

        if "ix_active_sessions_user_last_seen" not in existing_indexes:
            op.create_index(
                "ix_active_sessions_user_last_seen",
                "active_sessions",
                ["user_id", "last_seen_at"],
                unique=False,
            )

        # Index for expired session cleanup
        if "ix_active_sessions_expires_at" not in existing_indexes:
            op.create_index(
                "ix_active_sessions_expires_at",
                "active_sessions",
                ["expires_at"],
                unique=False,
            )

    # Push Subscriptions: Index for topic-based notifications
    if "push_subscriptions" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("push_subscriptions")
        }
        existing_columns = {
            col["name"] for col in inspector.get_columns("push_subscriptions")
        }

        # Partial index for active subscriptions by user
        # Only create if revoked_at column exists (legacy databases)
        if (
            "ix_push_subscriptions_user_active" not in existing_indexes
            and "revoked_at" in existing_columns
        ):
            op.create_index(
                "ix_push_subscriptions_user_active",
                "push_subscriptions",
                ["user_id"],
                unique=False,
                postgresql_where=sa.text("revoked_at IS NULL"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()

    if "push_subscriptions" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("push_subscriptions")
        }
        if "ix_push_subscriptions_user_active" in existing_indexes:
            op.drop_index(
                "ix_push_subscriptions_user_active", table_name="push_subscriptions"
            )

    if "active_sessions" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("active_sessions")
        }
        if "ix_active_sessions_expires_at" in existing_indexes:
            op.drop_index("ix_active_sessions_expires_at", table_name="active_sessions")
        if "ix_active_sessions_user_last_seen" in existing_indexes:
            op.drop_index(
                "ix_active_sessions_user_last_seen", table_name="active_sessions"
            )

    if "notifications" in existing_tables:
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("notifications")
        }
        if "ix_notifications_user_unread" in existing_indexes:
            op.drop_index("ix_notifications_user_unread", table_name="notifications")
        if "ix_notifications_user_created_desc" in existing_indexes:
            op.drop_index(
                "ix_notifications_user_created_desc", table_name="notifications"
            )
