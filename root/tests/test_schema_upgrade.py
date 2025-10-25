import asyncio
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.schema_upgrade import ensure_webauthn_attestation_columns


@pytest.fixture()
def sqlite_engine(tmp_path: Path) -> AsyncEngine:
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    """
                    CREATE TABLE mfa_webauthn_credentials (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        credential_id VARCHAR(255) NOT NULL,
                        public_key TEXT NOT NULL,
                        sign_count INTEGER NOT NULL DEFAULT 0,
                        transports TEXT,
                        device_name VARCHAR(255),
                        backed_up BOOLEAN NOT NULL DEFAULT 0,
                        clone_warning BOOLEAN NOT NULL DEFAULT 0,
                        created_at TIMESTAMP,
                        last_used_at TIMESTAMP,
                        is_active BOOLEAN NOT NULL DEFAULT 1
                    )
                    """
                )
            )

    asyncio.run(_setup())

    yield engine

    asyncio.run(engine.dispose())


def _get_columns(engine: AsyncEngine) -> set[str]:
    async def _inner() -> set[str]:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in sa.inspect(sync_conn).get_columns(
                        "mfa_webauthn_credentials"
                    )
                }
            )

    return asyncio.run(_inner())


def _get_indexes(engine: AsyncEngine) -> set[str]:
    async def _inner() -> set[str]:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: {
                    index["name"]
                    for index in sa.inspect(sync_conn).get_indexes(
                        "mfa_webauthn_credentials"
                    )
                }
            )

    return asyncio.run(_inner())


def test_ensure_webauthn_attestation_columns_adds_missing_fields(
    sqlite_engine: AsyncEngine,
) -> None:
    before_columns = _get_columns(sqlite_engine)
    assert "aaguid" not in before_columns

    asyncio.run(ensure_webauthn_attestation_columns(sqlite_engine))

    after_columns = _get_columns(sqlite_engine)
    assert {"aaguid", "attestation_format", "attestation_trust_score"}.issubset(
        after_columns
    )
    assert {"attestation_metadata", "metadata_warnings"}.issubset(after_columns)

    indexes = _get_indexes(sqlite_engine)
    assert "ix_mfa_webauthn_credentials_aaguid" in indexes

    # Second run should be a no-op and not raise.
    asyncio.run(ensure_webauthn_attestation_columns(sqlite_engine))
