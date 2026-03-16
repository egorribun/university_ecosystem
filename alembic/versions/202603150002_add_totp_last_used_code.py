"""Add last_used_code_hash and last_used_at to mfa_totp_enrollments.

MOD-W8-06 (audit 2026-03-15): Belt-and-suspenders TOTP replay prevention.

Adds two nullable columns to ``mfa_totp_enrollments``:

* ``last_used_code_hash`` — SHA-256 hex digest (VARCHAR 64) of the most
  recently accepted TOTP code for this enrollment.
* ``last_used_at`` — timestamp of that acceptance.

Together they allow ``verify_totp_for_user`` to reject an identical code
even in edge cases where the challenge token was already consumed (e.g. a
concurrent request racing the 30-second TOTP window).

Revision ID: 202603150002
Revises: 202603150001
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "202603150002"
down_revision: str | None = "202603150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mfa_totp_enrollments"
_COL_HASH = "last_used_code_hash"
_COL_AT = "last_used_at"


def upgrade() -> None:
    """Add last_used_code_hash and last_used_at columns."""
    op.add_column(
        _TABLE,
        sa.Column(
            _COL_HASH,
            sa.String(64),
            nullable=True,
            comment="SHA-256 hex digest of the last successfully verified TOTP code.",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            _COL_AT,
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of the last successful TOTP verification.",
        ),
    )


def downgrade() -> None:
    """Drop last_used_code_hash and last_used_at columns."""
    op.drop_column(_TABLE, _COL_AT)
    op.drop_column(_TABLE, _COL_HASH)
