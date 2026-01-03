"""Add composite index for chat message queries.

This index improves performance of get_chats() endpoint
which queries unread messages by chat_id, read_status, and sender_id.

Revision ID: 202512230001
Revises: 202512210001_add_session_fingerprint_columns
Create Date: 2025-12-23 10:30:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "202512230001_chat_message_index"
down_revision = "202512210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for unread message count queries:
    # SELECT COUNT(*) FROM messages WHERE chat_id = ? AND read_status = false AND sender_id != ?
    op.create_index(
        "ix_messages_chat_unread_sender",
        "messages",
        ["chat_id", "read_status", "sender_id"],
        unique=False,
    )

    # Index for ordering by created_at within a chat
    op.create_index(
        "ix_messages_chat_created_at",
        "messages",
        ["chat_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_chat_created_at", table_name="messages")
    op.drop_index("ix_messages_chat_unread_sender", table_name="messages")
