"""Create message_reactions table (Wave 206 message reactions)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300003"
down_revision: str | None = "202605300002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "message_reactions"
_INDEX_NAME = "ix_message_reactions_message_id"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Apply: create the message_reactions (user_id, message_id, emoji) child table."""
    bind = op.get_bind()

    if _table_exists(bind, _TABLE_NAME):
        return

    op.create_table(
        _TABLE_NAME,
        # UUID7 PK (Python-side default=generate_uuid7, matching the mixin) — the
        # repo's pg_insert applies the column default, so no server_default here.
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Idempotent reaction: one row per (user, message, emoji). The repo's
        # pg_insert(...).on_conflict_do_nothing targets this constraint.
        sa.UniqueConstraint(
            "user_id",
            "message_id",
            "emoji",
            name="uq_message_reactions_user_message_emoji",
        ),
    )
    # DEBT-02 pattern: dedicated message_id index for the get_messages
    # selectinload aggregation (WHERE message_id IN (…)); the unique constraint
    # is user_id-leading and does not serve it.
    op.create_index(_INDEX_NAME, _TABLE_NAME, ["message_id"])


def downgrade() -> None:
    """Revert: drop the message_reactions table."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
