"""Expand the MFA schema for bound email OTP challenges and delivery envelopes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "202608250001"
down_revision = "202607280001"
branch_labels = None
depends_on = None

_LOCK_ID = 824_250_001


def _has_column(bind: Any, table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _add_column_if_missing(bind: Any, table: str, column: sa.Column[Any]) -> None:
    if not _has_column(bind, table, str(column.name)):
        op.add_column(table, column)


def remediate_verified_email(
    bind: Any, *, user_id: Any, verified_at: datetime | None
) -> None:
    """Explicit operator helper; never infers verification from email presence."""
    if verified_at is None:
        raise ValueError("verified_at must come from durable verification evidence")
    users = sa.table(
        "users",
        sa.column("id"),
        sa.column("email_verified_at", sa.DateTime(timezone=True)),
    )
    existing = bind.execute(
        sa.select(users.c.email_verified_at).where(users.c.id == user_id)
    ).scalar_one_or_none()
    if existing is not None:
        if str(existing) == str(verified_at) or str(existing).replace(
            " ", "T"
        ).startswith(verified_at.replace(tzinfo=None).isoformat(timespec="seconds")):
            return
        raise ValueError("verified email remediation conflicts with durable evidence")
    result = bind.execute(
        users.update()
        .where(users.c.id == user_id)
        .values(email_verified_at=verified_at)
    )
    if getattr(result, "rowcount", 0) != 1:
        raise ValueError("user remediation target was not found")


def _upgrade_body(bind: Any) -> None:
    _add_column_if_missing(
        bind,
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "users",
        sa.Column("email_mfa_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "users",
        sa.Column("mfa_epoch", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        bind,
        "active_sessions",
        sa.Column("mfa_epoch", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        bind,
        "trusted_devices",
        sa.Column("mfa_epoch", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        bind,
        "trusted_devices",
        sa.Column("token_key_id", sa.String(64), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "trusted_devices",
        sa.Column("binding_digest", sa.String(64), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "mfa_totp_enrollments",
        sa.Column("last_used_timecode", sa.BigInteger(), nullable=True),
    )

    challenge_columns = (
        sa.Column("flow", sa.String(32), nullable=True),
        sa.Column("session_identifier", sa.String(128), nullable=True),
        sa.Column("client_fingerprint", sa.String(64), nullable=True),
        sa.Column("method", sa.String(20), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=True, server_default="1"),
        sa.Column(
            "trust_device_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("token_digest", sa.String(64), nullable=True),
        sa.Column("token_key_id", sa.String(64), nullable=True),
        sa.Column("recipient_digest", sa.String(64), nullable=True),
        sa.Column("otp_digest", sa.String(64), nullable=True),
        sa.Column("otp_key_id", sa.String(64), nullable=True),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in challenge_columns:
        _add_column_if_missing(bind, "mfa_challenges", column)
    # The expansion/runtime overlap must accept digest-only inserts while
    # immediately invalidating legacy plaintext-token challenges.
    op.alter_column("mfa_challenges", "token", nullable=True)
    bind.execute(
        sa.text(
            "UPDATE mfa_challenges SET consumed_at=CURRENT_TIMESTAMP, "
            "state='locked', payload=NULL, token=NULL "
            "WHERE token_digest IS NULL"
        )
    )

    tables = set(sa.inspect(bind).get_table_names())
    if "mfa_email_deliveries" not in tables:
        op.create_table(
            "mfa_email_deliveries",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("challenge_id", sa.UUID(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.String(255), nullable=False, unique=True),
            sa.Column("template", sa.String(64), nullable=False),
            sa.Column("locale", sa.String(2), nullable=False),
            sa.Column("kek_id", sa.String(64), nullable=False),
            sa.Column("envelope_nonce", sa.LargeBinary(12), nullable=True),
            sa.Column("envelope_ciphertext", sa.LargeBinary(), nullable=True),
            sa.Column("wrap_nonce", sa.LargeBinary(12), nullable=True),
            sa.Column("wrapped_dek", sa.LargeBinary(), nullable=True),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="pending"
            ),
            sa.Column(
                "attempt_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("lease_token", sa.String(64), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shredded_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["challenge_id"], ["mfa_challenges.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "challenge_id",
                "revision",
                name="uq_mfa_email_delivery_challenge_revision",
            ),
            sa.CheckConstraint(
                "locale IN ('en','ru')", name="ck_mfa_email_delivery_locale"
            ),
            sa.CheckConstraint(
                "status IN ('pending','sending','sent','cancelled')",
                name="ck_mfa_email_delivery_status",
            ),
            sa.CheckConstraint(
                "(status IN ('pending','sending') AND envelope_nonce IS NOT NULL "
                "AND envelope_ciphertext IS NOT NULL AND wrap_nonce IS NOT NULL "
                "AND wrapped_dek IS NOT NULL AND shredded_at IS NULL) OR "
                "(status IN ('sent','cancelled') AND envelope_nonce IS NULL "
                "AND envelope_ciphertext IS NULL AND wrap_nonce IS NULL "
                "AND wrapped_dek IS NULL AND shredded_at IS NOT NULL)",
                name="ck_mfa_email_delivery_envelope_lifecycle",
            ),
        )
        op.create_index(
            "ix_mfa_email_deliveries_challenge_id",
            "mfa_email_deliveries",
            ["challenge_id"],
        )
        op.create_index(
            "ix_mfa_email_deliveries_pending_created",
            "mfa_email_deliveries",
            ["created_at", "id"],
            postgresql_where=sa.text("status = 'pending'"),
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        bind.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _LOCK_ID}
        )
        bind.exec_driver_sql(
            "LOCK TABLE users, active_sessions, trusted_devices, mfa_challenges "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    _upgrade_body(bind)


def downgrade() -> None:
    # upgrade() permanently shreds legacy plaintext challenge tokens.  A
    # downgrade cannot reconstruct those values or restore a schema usable by
    # the legacy runtime, so fail before making any partial schema changes.
    raise RuntimeError(
        "email OTP MFA expansion is irreversible after plaintext token shredding"
    )
