"""Security audit 2026-02-26: schema hardening fixes.

Implements three schema-level changes identified in the security and architecture
audit:

1. **FailedLoginAttempt** (TD-3):
   Add ``ip_address`` and ``user_agent`` columns plus a composite index on
   ``(ip_address, attempted_at)`` so distributed brute-force attempts can be
   detected across rotating target emails from a single attacking IP.

2. **LoginHistory** (TD-2):
   Change ``latitude`` and ``longitude`` from ``VARCHAR(20)`` to
   ``NUMERIC(9, 6)``.  Storing coordinates as strings blocks PostGIS spatial
   queries and geo-analytics without an explicit CAST.  Numeric(9,6) covers
   ±179.999999° with six decimal places (≈ 11 cm precision).

3. **WebAuthnCredential** (OZ-1):
   Change ``public_key`` from unbounded ``TEXT`` to ``VARCHAR(4096)``.
   Without a bound an attacker with access to the WebAuthn registration
   endpoint could write arbitrarily large values, causing OOM when the
   credential list is fetched.  A COSE-encoded EC key is ≈ 512 B base64;
   RSA-4096 is ≈ 736 B base64 — 4 096 chars is a very generous safe limit.

Revision ID: 202602270003
Revises: 202602270002
Create Date: 2026-02-26 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202602270003"
down_revision: str | None = "202602270002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply all audit-2026-02-26 schema hardening changes."""

    # ── 1. failed_login_attempts ──────────────────────────────────────────────
    # TD-3: Add ip_address and user_agent to support distributed brute-force
    # detection. Both are nullable so that existing rows remain valid.
    with op.batch_alter_table("failed_login_attempts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ip_address",
                sa.String(45),
                nullable=True,
                comment="Source IP (IPv4/IPv6, max 45 chars). Nullable for backwards compatibility.",
            )
        )
        batch_op.add_column(
            sa.Column(
                "user_agent",
                sa.String(512),
                nullable=True,
            )
        )
        # Index allows fast "how many failures from this IP in last N seconds" queries.
        batch_op.create_index(
            "ix_failed_login_attempts_ip_attempted_at",
            ["ip_address", "attempted_at"],
        )

    # ── 2. login_history ─────────────────────────────────────────────────────
    # TD-2: lat/lon VARCHAR(20) → NUMERIC(9,6).
    # USING clause casts existing text values; NULL rows pass through unchanged.
    with op.batch_alter_table("login_history") as batch_op:
        batch_op.alter_column(
            "latitude",
            existing_type=sa.String(20),
            type_=sa.Numeric(9, 6),
            # PostgreSQL can coerce VARCHAR → NUMERIC automatically when the
            # stored value is a valid decimal string.  Rows with NULL latitude
            # remain NULL.  If any row contains an invalid non-numeric string
            # this migration will raise, exposing the data quality issue early.
            postgresql_using="latitude::numeric(9,6)",
            existing_nullable=True,
        )
        batch_op.alter_column(
            "longitude",
            existing_type=sa.String(20),
            type_=sa.Numeric(9, 6),
            postgresql_using="longitude::numeric(9,6)",
            existing_nullable=True,
        )

    # ── 3. webauthn_credentials ───────────────────────────────────────────────
    # OZ-1: public_key TEXT → VARCHAR(4096).
    # COSE EC key ≈ 512 B base64, RSA-4096 PSS ≈ 736 B base64.
    # 4 096 chars is a safe upper bound that stops unbounded payload abuse.
    with op.batch_alter_table("webauthn_credentials") as batch_op:
        batch_op.alter_column(
            "public_key",
            existing_type=sa.Text(),
            type_=sa.String(4096),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Revert audit-2026-02-26 schema changes."""

    # ── 3. webauthn_credentials — revert to TEXT ──────────────────────────────
    with op.batch_alter_table("webauthn_credentials") as batch_op:
        batch_op.alter_column(
            "public_key",
            existing_type=sa.String(4096),
            type_=sa.Text(),
            existing_nullable=False,
        )

    # ── 2. login_history — revert to VARCHAR ─────────────────────────────────
    with op.batch_alter_table("login_history") as batch_op:
        batch_op.alter_column(
            "latitude",
            existing_type=sa.Numeric(9, 6),
            type_=sa.String(20),
            postgresql_using="latitude::text",
            existing_nullable=True,
        )
        batch_op.alter_column(
            "longitude",
            existing_type=sa.Numeric(9, 6),
            type_=sa.String(20),
            postgresql_using="longitude::text",
            existing_nullable=True,
        )

    # ── 1. failed_login_attempts — remove added columns and index ─────────────
    with op.batch_alter_table("failed_login_attempts") as batch_op:
        batch_op.drop_index("ix_failed_login_attempts_ip_attempted_at")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_address")
