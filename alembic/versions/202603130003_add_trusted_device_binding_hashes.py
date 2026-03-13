"""Add ip_hash and ua_hash columns to trusted_devices for constant-time binding.

P1-W5-07 (audit 2026-03-13): The existing ip_address / user_agent columns store
raw values for audit/display purposes.  Two new SHA-256 hex-digest columns
(ip_hash, ua_hash) are added to enable constant-time comparison during token
verification without exposing raw IP or UA strings in comparison logic.

These columns are nullable so that pre-existing device records are not
invalidated on upgrade — the verification layer skips binding checks when
either the stored hash or the request context is absent.

Revision ID: 202603130003
Revises: 202603130002
Create Date: 2026-03-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202603130003"
down_revision: str | None = "202603130002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trusted_devices",
        sa.Column("ip_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "trusted_devices",
        sa.Column("ua_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trusted_devices", "ua_hash")
    op.drop_column("trusted_devices", "ip_hash")
