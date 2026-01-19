"""Drop legacy WebAuthn credential storage."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202509230001"
down_revision: str | None = "202509220001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mfa_webauthn_credentials"
_INDEXES = (
    "ix_mfa_webauthn_credentials_aaguid",
    "ix_mfa_webauthn_user_active",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for name in _INDEXES:
        if name in existing_indexes:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _TABLE not in inspector.get_table_names():
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "credential_id", sa.String(length=255), nullable=False, unique=True
            ),
            sa.Column("public_key", sa.Text(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("transports", sa.JSON(), nullable=True),
            sa.Column("device_name", sa.String(length=255), nullable=True),
            sa.Column(
                "backed_up",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "clone_warning",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("aaguid", sa.String(length=64), nullable=True),
            sa.Column("attestation_format", sa.String(length=64), nullable=True),
            sa.Column("attestation_trust_score", sa.Integer(), nullable=True),
            sa.Column("attestation_metadata", sa.JSON(), nullable=True),
            sa.Column("metadata_warnings", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    op.create_index(
        "ix_mfa_webauthn_user_active",
        _TABLE,
        ["user_id", "is_active"],
    )
    op.create_index("ix_mfa_webauthn_credentials_aaguid", _TABLE, ["aaguid"])
