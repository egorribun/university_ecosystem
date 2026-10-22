"""PostgreSQL acceptance for TOTP key rotation and row-lock behavior."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.utils.encryption import TotpEncryptionError, reset_cached_cipher
from scripts.rotate_totp_encryption_keys import rotate_totp_enrollments
from tests.integration.owned_postgres import _LoopbackMigrationPostgres

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_OPERATOR_URL = os.getenv("MIGRATION_ROUNDTRIP_DATABASE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN and _OPERATOR_URL),
        reason=(
            "requires RUN_INTEGRATION_TESTS=1 and the owned loopback "
            "MIGRATION_ROUNDTRIP_DATABASE_URL"
        ),
    ),
]


@pytest_asyncio.fixture
async def postgres_totp_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    """Use one generated schema in the root-owned disposable PG database."""
    postgres = _LoopbackMigrationPostgres(_OPERATOR_URL)
    database_url = postgres.get_connection_url(driver="asyncpg")
    schema_name = f"totp_rotation_{uuid4().hex}"
    admin_engine = create_async_engine(
        database_url,
        connect_args={
            "server_settings": {
                "lock_timeout": "1s",
                "statement_timeout": "10s",
            },
            "command_timeout": 12.0,
        },
    )
    scoped_engine: AsyncEngine | None = None
    schema_created = False
    try:
        async with admin_engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: sync_connection.execute(
                    CreateSchema(schema_name)
                )
            )
        schema_created = True
        scoped_engine = create_async_engine(
            database_url,
            connect_args={
                "server_settings": {
                    "search_path": schema_name,
                    "lock_timeout": "250ms",
                    "statement_timeout": "3s",
                },
                "command_timeout": 5.0,
            },
        )
        async with scoped_engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE mfa_totp_enrollments ("
                    "id uuid PRIMARY KEY, secret text NOT NULL)"
                )
            )
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "secret_key", "synthetic-pg-test-secret-key")
        monkeypatch.setattr(settings, "spotify_token_secret", "")
        monkeypatch.setattr(
            settings,
            "mfa_totp_encryption_keys",
            "",
        )
        monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "")
        reset_cached_cipher()
        factory = async_sessionmaker(scoped_engine, expire_on_commit=False)
        yield scoped_engine, factory
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        if schema_created:
            async with admin_engine.begin() as connection:
                await connection.run_sync(
                    lambda sync_connection: sync_connection.execute(
                        DropSchema(schema_name, cascade=True)
                    )
                )
        await admin_engine.dispose()
        reset_cached_cipher()


def _configure_keyring(
    monkeypatch: pytest.MonkeyPatch, active_key: str, legacy_key: str
) -> None:
    monkeypatch.setattr(
        settings,
        "mfa_totp_encryption_keys",
        f"active:{active_key},legacy:{legacy_key}",
    )
    monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "active")
    reset_cached_cipher()


async def _insert_rows(engine: AsyncEngine, rows: list[tuple[UUID, str]]) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO mfa_totp_enrollments (id, secret) "
                "VALUES (:row_id, :secret)"
            ),
            [{"row_id": row_id, "secret": secret} for row_id, secret in rows],
        )


async def _stored_rows(engine: AsyncEngine) -> dict[UUID, str]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id, secret FROM mfa_totp_enrollments ORDER BY id")
        )
        return {row[0]: row[1] for row in result.all()}


@pytest.mark.asyncio
async def test_postgres_rotation_is_idempotent_and_rolls_back_unknown_row_batch(
    postgres_totp_scope: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = postgres_totp_scope
    active_key = Fernet.generate_key().decode("ascii")
    legacy_key = Fernet.generate_key().decode("ascii")
    unknown_key = Fernet.generate_key().decode("ascii")
    _configure_keyring(monkeypatch, active_key, legacy_key)
    active_uuid = UUID("00000000-0000-4000-8000-000000000001")
    legacy_uuid = UUID("00000000-0000-4000-8000-000000000002")
    active_token = (
        Fernet(active_key.encode("ascii")).encrypt(b"active-seed").decode("ascii")
    )
    legacy_token = (
        Fernet(legacy_key.encode("ascii")).encrypt(b"legacy-seed").decode("ascii")
    )
    await _insert_rows(
        engine, [(active_uuid, active_token), (legacy_uuid, legacy_token)]
    )

    dry_run = await rotate_totp_enrollments(factory, dry_run=True, batch_size=2)
    assert (dry_run.scanned, dry_run.would_rotate, dry_run.already_active) == (2, 1, 1)
    assert await _stored_rows(engine) == {
        active_uuid: active_token,
        legacy_uuid: legacy_token,
    }

    applied = await rotate_totp_enrollments(factory, dry_run=False, batch_size=2)
    assert (applied.scanned, applied.rotated, applied.already_active) == (2, 1, 1)
    second_pass = await rotate_totp_enrollments(factory, dry_run=False, batch_size=2)
    assert (second_pass.scanned, second_pass.rotated, second_pass.already_active) == (
        2,
        0,
        2,
    )
    rotated_rows = await _stored_rows(engine)
    assert (
        Fernet(active_key.encode("ascii")).decrypt(
            rotated_rows[active_uuid].encode("ascii")
        )
        == b"active-seed"
    )
    assert (
        Fernet(active_key.encode("ascii")).decrypt(
            rotated_rows[legacy_uuid].encode("ascii")
        )
        == b"legacy-seed"
    )

    rollback_uuid = UUID("00000000-0000-4000-8000-000000000003")
    unknown_uuid = UUID("00000000-0000-4000-8000-000000000004")
    rollback_token = (
        Fernet(legacy_key.encode("ascii")).encrypt(b"rollback-seed").decode("ascii")
    )
    unknown_token = (
        Fernet(unknown_key.encode("ascii")).encrypt(b"unknown-seed").decode("ascii")
    )
    await _insert_rows(
        engine, [(rollback_uuid, rollback_token), (unknown_uuid, unknown_token)]
    )

    with pytest.raises(TotpEncryptionError, match="cannot be decrypted"):
        await rotate_totp_enrollments(factory, dry_run=False, batch_size=2)

    final_rows = await _stored_rows(engine)
    assert final_rows[rollback_uuid] == rollback_token
    assert final_rows[unknown_uuid] == unknown_token


@pytest.mark.asyncio
async def test_postgres_apply_uses_bounded_row_lock_wait(
    postgres_totp_scope: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = postgres_totp_scope
    active_key = Fernet.generate_key().decode("ascii")
    legacy_key = Fernet.generate_key().decode("ascii")
    _configure_keyring(monkeypatch, active_key, legacy_key)
    row_id = UUID("00000000-0000-4000-8000-000000000005")
    old_token = (
        Fernet(legacy_key.encode("ascii")).encrypt(b"locked-seed").decode("ascii")
    )
    await _insert_rows(engine, [(row_id, old_token)])

    async with factory() as lock_session:
        async with lock_session.begin():
            await lock_session.execute(
                text(
                    "SELECT id FROM mfa_totp_enrollments WHERE id = :row_id FOR UPDATE"
                ),
                {"row_id": row_id},
            )
            with pytest.raises(DBAPIError) as lock_error:
                await asyncio.wait_for(
                    rotate_totp_enrollments(factory, dry_run=False, batch_size=1),
                    timeout=4,
                )
            driver_error = lock_error.value.orig
            sqlstate = getattr(driver_error, "sqlstate", None)
            if sqlstate is None:
                sqlstate = getattr(
                    getattr(driver_error, "__cause__", None), "sqlstate", None
                )
            assert sqlstate == "55P03"

    assert (await _stored_rows(engine))[row_id] == old_token
