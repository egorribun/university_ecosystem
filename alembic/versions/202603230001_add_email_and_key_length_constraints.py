"""Add length constraints to email and signing key columns.

Audit 2026-03-23: Initial schema migrations created email columns
as sa.String() (unbounded TEXT in PostgreSQL).  The ORM models define
String(254) (RFC 5321 compliant maximum) but the database-level constraint was
missing, allowing values up to ~8 KB — negating the storage-amplification
protection intended by the model definition.

Tables affected:
  - users.email                      (model: String(254))
  - failed_login_attempts.email      (model: String(254))
  - email_change_tokens.new_email    (model: String(254))
  - active_sessions.signing_key      (model: String(128))

The ALTER COLUMN statements will fail with a DataError if any existing value
exceeds the new length.  Run the pre-flight query before applying:

    SELECT COUNT(*) FROM users WHERE length(email) > 254;
    SELECT COUNT(*) FROM failed_login_attempts WHERE length(email) > 254;
    SELECT COUNT(*) FROM email_change_tokens WHERE length(new_email) > 254;
    SELECT COUNT(*) FROM active_sessions WHERE length(signing_key) > 128;

All should return 0 on a healthy database.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "202603230001"
down_revision: str | None = "202603170003"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # Never modify historical migrations — add forward migration only.
    op.alter_column(
        "users",
        "email",
        type_=sa.String(254),
        existing_nullable=False,
        existing_type=sa.String(),
    )
    op.alter_column(
        "failed_login_attempts",
        "email",
        type_=sa.String(254),
        existing_nullable=True,
        existing_type=sa.String(),
    )
    op.alter_column(
        "email_change_tokens",
        "new_email",
        type_=sa.String(254),
        existing_nullable=False,
        existing_type=sa.String(),
    )
    # signing_key — token_urlsafe(32) produces 43 chars; String(128)
    # gives 3x headroom for future key-format changes without migration churn.
    op.alter_column(
        "active_sessions",
        "signing_key",
        type_=sa.String(128),
        existing_nullable=False,
        existing_type=sa.String(),
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "email",
        type_=sa.String(),
        existing_nullable=False,
        existing_type=sa.String(254),
    )
    op.alter_column(
        "failed_login_attempts",
        "email",
        type_=sa.String(),
        existing_nullable=True,
        existing_type=sa.String(254),
    )
    op.alter_column(
        "email_change_tokens",
        "new_email",
        type_=sa.String(),
        existing_nullable=False,
        existing_type=sa.String(254),
    )
    op.alter_column(
        "active_sessions",
        "signing_key",
        type_=sa.String(),
        existing_nullable=False,
        existing_type=sa.String(128),
    )
