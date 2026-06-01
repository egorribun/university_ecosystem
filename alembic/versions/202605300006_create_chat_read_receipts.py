"""Create chat_read_receipts table (Wave 210 G2 per-recipient read receipts)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300006"
down_revision: str | None = "202605300005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "chat_read_receipts"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Apply: create the chat_read_receipts (chat_id, user_id, last_read_at) table.

    Wave 210 G2 — per-recipient read high-water-mark for GROUP chats. DMs keep
    Message.read_status (Option A); this table is group-only in practice.
    """
    bind = op.get_bind()

    if _table_exists(bind, _TABLE_NAME):
        return

    op.create_table(
        _TABLE_NAME,
        # UUID7 PK (Python-side default=generate_uuid7, matching the mixin) — the
        # repo's Core insert applies the column default, so no server_default here.
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chat_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        # One row per (chat, user); makes mark_messages_read's check-then-
        # (UPDATE|INSERT) upsert idempotent. The chat_id-leading unique key also
        # serves get_read_receipts (WHERE chat_id) + the unread-CTE join, so no
        # standalone index is needed (unlike message_reactions, whose unique key
        # is user_id-leading).
        sa.UniqueConstraint(
            "chat_id", "user_id", name="uq_chat_read_receipts_chat_user"
        ),
    )


def downgrade() -> None:
    """Revert: drop the chat_read_receipts table."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    op.drop_table(_TABLE_NAME)
