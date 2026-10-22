from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.utils.encryption import TotpEncryptionError, reset_cached_cipher
from scripts.rotate_totp_encryption_keys import (
    TotpRotationConflict,
    rotate_totp_enrollments,
)


@pytest.mark.asyncio
async def test_rotation_dry_run_apply_and_second_pass_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    legacy_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        settings,
        "mfa_totp_encryption_keys",
        f"active:{active_key},legacy:{legacy_key}",
    )
    monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "active")
    reset_cached_cipher()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    active_id = str(uuid4())
    legacy_id = str(uuid4())
    active_token = (
        Fernet(active_key.encode("ascii")).encrypt(b"active-seed").decode("ascii")
    )
    legacy_token = (
        Fernet(legacy_key.encode("ascii")).encrypt(b"legacy-seed").decode("ascii")
    )

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE mfa_totp_enrollments "
                    "(id TEXT PRIMARY KEY, secret TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO mfa_totp_enrollments (id, secret) "
                    "VALUES (:id, :secret)"
                ),
                [
                    {"id": active_id, "secret": active_token},
                    {"id": legacy_id, "secret": legacy_token},
                ],
            )

        dry_run = await rotate_totp_enrollments(factory, dry_run=True, batch_size=1)
        assert dry_run.scanned == 2
        assert dry_run.would_rotate == 1
        assert dry_run.rotated == 0
        assert dry_run.already_active == 1
        async with factory() as session:
            unchanged = list(
                (
                    await session.execute(
                        text("SELECT id, secret FROM mfa_totp_enrollments ORDER BY id")
                    )
                ).mappings()
            )
        assert {row["secret"] for row in unchanged} == {active_token, legacy_token}

        applied = await rotate_totp_enrollments(factory, dry_run=False, batch_size=1)
        assert applied.scanned == 2
        assert applied.rotated == 1
        assert applied.already_active == 1
        second_pass = await rotate_totp_enrollments(
            factory, dry_run=False, batch_size=1
        )
        assert second_pass.scanned == 2
        assert second_pass.rotated == 0
        assert second_pass.already_active == 2
        async with factory() as session:
            values = list(
                (
                    await session.execute(
                        text("SELECT id, secret FROM mfa_totp_enrollments ORDER BY id")
                    )
                ).mappings()
            )
        decrypted_by_id = {
            row["id"]: Fernet(active_key.encode("ascii")).decrypt(
                row["secret"].encode("ascii")
            )
            for row in values
        }
        assert decrypted_by_id == {
            active_id: b"active-seed",
            legacy_id: b"legacy-seed",
        }
    finally:
        await engine.dispose()
        reset_cached_cipher()


@pytest.mark.asyncio
async def test_unknown_ciphertext_rolls_back_the_current_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    legacy_key = Fernet.generate_key().decode("ascii")
    unknown_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        settings,
        "mfa_totp_encryption_keys",
        f"active:{active_key},legacy:{legacy_key}",
    )
    monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "active")
    reset_cached_cipher()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_token = (
        Fernet(legacy_key.encode("ascii")).encrypt(b"first-seed").decode("ascii")
    )
    second_token = (
        Fernet(unknown_key.encode("ascii")).encrypt(b"second-seed").decode("ascii")
    )

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE mfa_totp_enrollments "
                    "(id TEXT PRIMARY KEY, secret TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO mfa_totp_enrollments (id, secret) "
                    "VALUES (:id, :secret)"
                ),
                [
                    {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "secret": first_token,
                    },
                    {
                        "id": "00000000-0000-0000-0000-000000000002",
                        "secret": second_token,
                    },
                ],
            )

        with pytest.raises(TotpEncryptionError, match="cannot be decrypted"):
            await rotate_totp_enrollments(factory, dry_run=False, batch_size=2)

        async with factory() as session:
            values = list(
                (
                    await session.execute(
                        text("SELECT secret FROM mfa_totp_enrollments ORDER BY id")
                    )
                ).scalars()
            )
        assert values == [first_token, second_token]
    finally:
        await engine.dispose()
        reset_cached_cipher()


@pytest.mark.asyncio
async def test_compare_and_swap_conflict_rolls_back_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    legacy_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        settings,
        "mfa_totp_encryption_keys",
        f"active:{active_key},legacy:{legacy_key}",
    )
    monkeypatch.setattr(settings, "mfa_totp_active_encryption_key_id", "active")
    reset_cached_cipher()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    old_token = Fernet(legacy_key.encode("ascii")).encrypt(b"seed").decode("ascii")

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE mfa_totp_enrollments "
                    "(id TEXT PRIMARY KEY, secret TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO mfa_totp_enrollments (id, secret) "
                    "VALUES (:id, :secret)"
                ),
                {"id": "00000000-0000-0000-0000-000000000001", "secret": old_token},
            )
            await connection.execute(
                text(
                    "CREATE TRIGGER ignore_totp_update BEFORE UPDATE "
                    "ON mfa_totp_enrollments BEGIN SELECT RAISE(IGNORE); END"
                )
            )

        with pytest.raises(TotpRotationConflict, match="changed during rotation"):
            await rotate_totp_enrollments(factory, dry_run=False, batch_size=1)

        async with factory() as session:
            stored = await session.scalar(
                text("SELECT secret FROM mfa_totp_enrollments")
            )
        assert stored == old_token
    finally:
        await engine.dispose()
        reset_cached_cipher()
