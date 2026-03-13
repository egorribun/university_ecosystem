"""Add explicit state machine column to mfa_challenges.

TD-W5-01: Replaces the implicit dual-null convention (consumed_at/locked_at)
with a single `state` enum column for audit clarity and type-safety.
Also adds the `locked_at` column that the challenge.py lock logic references
but was previously missing from the schema.

Revision ID: 202603130001
Revises: 202603070001
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "202603130001"
down_revision: str | None = "202603070001"
branch_labels = None
depends_on = None

_ENUM_NAME = "challenge_state_enum"
_ENUM_VALUES = ("pending", "consumed", "locked", "expired")


def upgrade() -> None:
    # Create the enum type
    challenge_state = sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME)
    challenge_state.create(op.get_bind(), checkfirst=True)

    # Add locked_at column (was referenced in challenge.py but never in schema)
    op.add_column(
        "mfa_challenges",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add state column with server default = 'pending'
    op.add_column(
        "mfa_challenges",
        sa.Column(
            "state",
            sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME, create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )

    # Backfill existing rows based on consumed_at
    op.execute(
        "UPDATE mfa_challenges SET state = 'consumed' WHERE consumed_at IS NOT NULL"
    )

    op.create_index(
        "ix_mfa_challenges_state",
        "mfa_challenges",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_challenges_state", table_name="mfa_challenges")
    op.drop_column("mfa_challenges", "state")
    op.drop_column("mfa_challenges", "locked_at")

    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
