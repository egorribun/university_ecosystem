"""Add attestation metadata fields to WebAuthn credentials."""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202507310001"
down_revision: str | None = "202507300001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mfa_webauthn_credentials"


def _column_names(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {table_name for table_name in inspector.get_table_names()}

    if _TABLE not in tables:
        return

    columns = _column_names(inspector, _TABLE)

    if "aaguid" not in columns:
        op.add_column(_TABLE, sa.Column("aaguid", sa.String(length=64), nullable=True))
        columns.add("aaguid")

    if "attestation_format" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("attestation_format", sa.String(length=64), nullable=True),
        )
    if "attestation_trust_score" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("attestation_trust_score", sa.Integer(), nullable=True),
        )
    if "attestation_metadata" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("attestation_metadata", sa.JSON(), nullable=True),
        )
    if "metadata_warnings" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("metadata_warnings", sa.JSON(), nullable=True),
        )

    indexes = _index_names(sa.inspect(bind), _TABLE)
    if "aaguid" in columns and "ix_mfa_webauthn_credentials_aaguid" not in indexes:
        op.create_index("ix_mfa_webauthn_credentials_aaguid", _TABLE, ["aaguid"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {table_name for table_name in inspector.get_table_names()}

    if _TABLE not in tables:
        return

    indexes = _index_names(inspector, _TABLE)
    if "ix_mfa_webauthn_credentials_aaguid" in indexes:
        op.drop_index("ix_mfa_webauthn_credentials_aaguid", table_name=_TABLE)

    columns = _column_names(inspector, _TABLE)
    for column_name in [
        "metadata_warnings",
        "attestation_metadata",
        "attestation_trust_score",
        "attestation_format",
        "aaguid",
    ]:
        if column_name in columns:
            op.drop_column(_TABLE, column_name)
