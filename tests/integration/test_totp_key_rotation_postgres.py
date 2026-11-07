"""PostgreSQL acceptance for TOTP key rotation and row-lock behavior."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.utils.encryption import TotpEncryptionError, reset_cached_cipher
from scripts.rotate_totp_encryption_keys import rotate_totp_enrollments
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

_USER_ID = uuid4()
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="signal", func_only=False),
    pytest.mark.skipif(not _RUN, reason="requires RUN_INTEGRATION_TESTS=1"),
]


@pytest.fixture(autouse=True)
def rotation_watchdog(request: pytest.FixtureRequest) -> None:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "TOTP rotation tests require --timeout-disable-debugger-detection"
    )


@pytest_asyncio.fixture
async def postgres_totp_scope(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    """Exercise the actual baseline on an active owned server lease only."""
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        tenant = uuid4()
        role = f"totp_rotation_{uuid4().hex}"
        admin = create_engine(
            baseline.url,
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with admin.begin() as connection:
                connection.execute(
                    text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
                )
                connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
                connection.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE ON public.mfa_totp_enrollments "
                        f'TO "{role}"'
                    )
                )
                connection.execute(
                    text("INSERT INTO tenants (id,name,slug) VALUES (:id,:name,:slug)"),
                    {
                        "id": tenant,
                        "name": "TOTP rotation contract",
                        "slug": uuid4().hex,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO users (id,email,hashed_password,tenant_id) "
                        "VALUES (:id,:email,:credential,:tenant)"
                    ),
                    {
                        "id": _USER_ID,
                        "email": f"{_USER_ID}@example.invalid",
                        "credential": f"!{uuid4()}",
                        "tenant": tenant,
                    },
                )
                foreign_keys = inspect(connection).get_foreign_keys(
                    "mfa_totp_enrollments"
                )
                assert any(
                    key["constrained_columns"] == ["user_id"]
                    and key["referred_table"] == "users"
                    and key["options"]["ondelete"] == "CASCADE"
                    for key in foreign_keys
                )
        finally:
            admin.dispose()

        engine = create_async_engine(
            baseline.url.set(drivername="postgresql+asyncpg", query={}),
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 5,
                "server_settings": {
                    "lock_timeout": "250ms",
                    "statement_timeout": "3s",
                    "idle_in_transaction_session_timeout": "10s",
                },
            },
        )

        @event.listens_for(engine.sync_engine, "begin")
        def restricted_transaction(connection) -> None:
            # Covers raw fixture connections and every rotation batch, without
            # depending on a synthetic table or installing a global listener.
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            assert connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls, "
                    "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one() == (role, False, False, False)
            assert (
                connection.scalar(
                    text("SELECT has_table_privilege(current_user, 'users', 'SELECT')")
                )
                is False
            )

        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "secret_key", "synthetic-pg-test-secret-key")
        monkeypatch.setattr(settings, "spotify_token_secret", "")
        monkeypatch.setattr(settings, "mfa_totp_encryption_keys", "")
        monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "")
        reset_cached_cipher()
        try:
            yield engine, async_sessionmaker(engine, expire_on_commit=False)
        finally:
            try:
                await engine.dispose()
            finally:
                reset_cached_cipher()
    assert request.getfixturevalue("default_database_guard") == []


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
                "INSERT INTO mfa_totp_enrollments (id, secret, user_id) "
                "VALUES (:row_id, :secret, :user_id)"
            ),
            [
                {"row_id": row_id, "secret": secret, "user_id": _USER_ID}
                for row_id, secret in rows
            ],
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
