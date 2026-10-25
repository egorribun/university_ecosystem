"""Add private durable chat-send receipts with owner and membership isolation."""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "202610250001"
down_revision = "202610200001"
branch_labels = None
depends_on = None

downgrade_policy = "irreversible"
downgrade_reason = (
    "Dropping chat send receipts can discard committed idempotency history "
    "and permit duplicate messages"
)


def _current_schema(bind: sa.Connection) -> str:
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
    if not isinstance(schema, str) or not schema:
        raise RuntimeError("Cannot resolve current schema for chat send receipts")
    return schema


def _emit_receipt_rls(operations: Any) -> None:
    operations.execute(
        sa.text("ALTER TABLE chat_send_receipts ENABLE ROW LEVEL SECURITY")
    )
    operations.execute(
        sa.text("ALTER TABLE chat_send_receipts FORCE ROW LEVEL SECURITY")
    )
    predicate = """
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        AND EXISTS (
            SELECT 1
            FROM chat_participants AS participant
            JOIN chats AS chat ON chat.id = participant.chat_id
            WHERE participant.chat_id = chat_send_receipts.chat_id
              AND participant.user_id = chat_send_receipts.user_id
        )
    """
    operations.execute(
        sa.text(
            "CREATE POLICY chat_send_receipts_owner_participant "
            "ON chat_send_receipts FOR ALL TO PUBLIC "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("Chat send receipt migration requires online PostgreSQL")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Chat send receipt migration requires PostgreSQL")
    schema = _current_schema(bind)
    if sa.inspect(bind).has_table("chat_send_receipts", schema=schema):
        raise RuntimeError("Existing chat send receipt tables require manual review")
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    op.create_table(
        "chat_send_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_id",
            "user_id",
            "key_digest",
            name="uq_chat_send_receipts_chat_user_key",
        ),
    )
    op.create_index(
        "ix_chat_send_receipts_message_id", "chat_send_receipts", ["message_id"]
    )
    op.create_index("ix_chat_send_receipts_user_id", "chat_send_receipts", ["user_id"])
    op.create_index(
        "ix_chat_send_receipts_expires_at", "chat_send_receipts", ["expires_at", "id"]
    )
    _emit_receipt_rls(op)


def downgrade() -> None:
    raise RuntimeError(
        "Dropping chat send receipts can discard committed idempotency history "
        "and permit duplicate messages"
    )
