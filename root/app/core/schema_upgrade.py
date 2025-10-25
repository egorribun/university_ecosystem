"""Utilities for applying lightweight schema upgrades at runtime."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_TABLE_NAME = "mfa_webauthn_credentials"
_INDEX_NAME = "ix_mfa_webauthn_credentials_aaguid"

_COLUMN_DEFINITIONS: Mapping[str, Mapping[str, str]] = {
    "aaguid": {"default": "VARCHAR(64)"},
    "attestation_format": {"default": "VARCHAR(64)"},
    "attestation_trust_score": {"default": "INTEGER"},
    "attestation_metadata": {"default": "JSON", "sqlite": "TEXT"},
    "metadata_warnings": {"default": "JSON", "sqlite": "TEXT"},
}


def _column_sql(dialect: str, column: str) -> str:
    overrides = _COLUMN_DEFINITIONS[column]
    return overrides.get(dialect, overrides["default"])


def _ensure_webauthn_columns(sync_conn: Connection) -> None:
    inspector = sa.inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if _TABLE_NAME not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns(_TABLE_NAME)}

    for column_name in _COLUMN_DEFINITIONS:
        if column_name in columns:
            continue
        column_type = _column_sql(sync_conn.dialect.name, column_name)
        logger.info(
            "Adding missing column %s.%s (%s)",
            _TABLE_NAME,
            column_name,
            column_type,
        )
        sync_conn.execute(
            sa.text(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {column_name} {column_type}")
        )
        columns.add(column_name)

    indexes = {index["name"] for index in inspector.get_indexes(_TABLE_NAME)}
    if _INDEX_NAME in indexes or "aaguid" not in columns:
        return

    logger.info("Creating missing index %s on %s", _INDEX_NAME, _TABLE_NAME)
    sync_conn.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} ON {_TABLE_NAME} (aaguid)")
    )


async def ensure_webauthn_attestation_columns(engine: AsyncEngine) -> None:
    """Ensure WebAuthn attestation columns exist for development databases."""

    try:
        async with engine.begin() as conn:
            await conn.run_sync(_ensure_webauthn_columns)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to ensure WebAuthn attestation columns exist")
