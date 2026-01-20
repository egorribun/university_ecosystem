"""fix sender_id type

Revision ID: fix_sender_id_type
Revises: 96809b6dc35d
Create Date: 2025-11-23 02:17:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_sender_id_type"
down_revision: str | None = "96809b6dc35d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    # Check if tables exist (may not exist on fresh databases)
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Alter sender_id column type from VARCHAR to INTEGER
    if "messages" in existing_tables:
        columns = {c["name"]: c for c in inspector.get_columns("messages")}
        if "sender_id" in columns:
            current_type = str(columns["sender_id"]["type"]).upper()
            if "VARCHAR" in current_type:
                op.execute(
                    "ALTER TABLE messages ALTER COLUMN sender_id TYPE INTEGER "
                    "USING sender_id::INTEGER"
                )

    # Also need to fix the chat_participants user_id if it's wrong
    if "chat_participants" in existing_tables:
        columns = {c["name"]: c for c in inspector.get_columns("chat_participants")}
        if "user_id" in columns:
            current_type = str(columns["user_id"]["type"]).upper()
            if "VARCHAR" in current_type:
                op.execute(
                    "ALTER TABLE chat_participants ALTER COLUMN user_id TYPE INTEGER "
                    "USING user_id::INTEGER"
                )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if bind.dialect.name == "sqlite":
        if "messages" in existing_tables:
            columns = {c["name"]: c for c in inspector.get_columns("messages")}
            if "sender_id" in columns and not isinstance(
                columns["sender_id"]["type"], sa.VARCHAR
            ):
                with op.batch_alter_table("messages") as batch_op:
                    batch_op.alter_column("sender_id", type_=sa.VARCHAR())
        if "chat_participants" in existing_tables:
            columns = {c["name"]: c for c in inspector.get_columns("chat_participants")}
            if "user_id" in columns and not isinstance(
                columns["user_id"]["type"], sa.VARCHAR
            ):
                with op.batch_alter_table("chat_participants") as batch_op:
                    batch_op.alter_column("user_id", type_=sa.VARCHAR())
    else:
        if "messages" in existing_tables:
            columns = {c["name"]: c for c in inspector.get_columns("messages")}
            if "sender_id" in columns:
                current_type = str(columns["sender_id"]["type"]).upper()
                if "INTEGER" in current_type or "INT" in current_type:
                    op.execute(
                        "ALTER TABLE messages ALTER COLUMN sender_id TYPE VARCHAR"
                    )
        if "chat_participants" in existing_tables:
            columns = {c["name"]: c for c in inspector.get_columns("chat_participants")}
            if "user_id" in columns:
                current_type = str(columns["user_id"]["type"]).upper()
                if "INTEGER" in current_type or "INT" in current_type:
                    op.execute(
                        "ALTER TABLE chat_participants "
                        "ALTER COLUMN user_id TYPE VARCHAR"
                    )
