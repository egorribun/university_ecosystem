"""Add private ownership keys for idempotent synthetic demo users and chats."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202609300001"
down_revision: str | None = "202609250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL unique constraints permit many NULL values, so ordinary rows
    # remain outside the demo-seed identity namespace.
    #
    # Existing user rows intentionally remain unmarked. In particular, do not
    # infer primary-demo ownership from the canonical email: a real account may
    # already occupy it. The seeder fails closed in that case. Recover an old
    # seeded account only after an operator verifies its provenance, then set
    # demo_seed_key to `ue-demo-v1:user:primary-owner` in a reviewed one-off
    # transaction; never mark an account based on its email alone.
    op.add_column(
        "users",
        sa.Column("demo_seed_key", sa.String(length=96), nullable=True),
    )
    op.create_unique_constraint("uq_users_demo_seed_key", "users", ["demo_seed_key"])
    op.add_column(
        "chats",
        sa.Column("demo_seed_key", sa.String(length=96), nullable=True),
    )
    op.create_unique_constraint("uq_chats_demo_seed_key", "chats", ["demo_seed_key"])


def downgrade() -> None:
    # Drop only the private marker schema. Chat/message/user rows remain intact.
    # If code is upgraded again, the demo seeder fails closed on the reserved
    # peer identities and any matching/partial chat membership rather than
    # adopting or duplicating records whose ownership key was removed.
    op.drop_constraint("uq_chats_demo_seed_key", "chats", type_="unique")
    op.drop_column("chats", "demo_seed_key")
    op.drop_constraint("uq_users_demo_seed_key", "users", type_="unique")
    op.drop_column("users", "demo_seed_key")
