"""TD-W8-07 — TOTP secret encryption-at-rest regression tests.

These tests guard against accidental removal of EncryptedString() from
MfaTotpEnrollment.secret and against recovery codes being stored as plaintext.

If either test fails it means:
  - MfaTotpEnrollment.secret is no longer encrypted at the ORM level, OR
  - RecoveryCode.code_hash is no longer hashed before storage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.auth import mfa

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_totp_secret_is_encrypted_in_db(db_session, user_factory):
    """The raw 'secret' column value stored in the DB must differ from the
    plaintext secret returned to the caller (EncryptedString transparently
    encrypts on write and decrypts on read).

    TD-W8-07: If EncryptedString() is removed, the ORM column becomes a plain
    String and this assertion fails — alerting us to the regression before it
    reaches production.
    """
    user = await user_factory()

    enrollment, plaintext_secret, _otpauth = await mfa.start_totp_enrollment(
        db_session,
        user=user,
        label="test-device",
    )
    await db_session.flush()

    # Read the raw column value from the DB, bypassing ORM-level decryption.
    result = await db_session.execute(
        text("SELECT secret FROM mfa_totp_enrollments WHERE id = :id"),
        {"id": enrollment.id.hex},  # SQLite stores UUID as 32-char hex without dashes
    )
    raw_value = result.scalar_one()

    assert raw_value is not None, (
        "secret column must not be NULL after enrollment flush"
    )
    assert raw_value != plaintext_secret, (
        "Raw DB value equals the plaintext TOTP secret — "
        "EncryptedString encryption-at-rest is not working. "
        "Check that MfaTotpEnrollment.secret still uses EncryptedString()."
    )


async def test_recovery_codes_are_hashed_in_db(db_session, user_factory):
    """Recovery codes must be stored as Argon2id hashes, never as plaintext.

    TD-W8-07: RecoveryCode.code_hash stores the Argon2id hash of each code.
    If the hashing step is accidentally removed, the raw code would appear in
    the DB and this assertion would fail.
    """
    user = await user_factory()

    plaintext_codes = await mfa.generate_recovery_codes(
        db_session,
        user=user,
        fresh_mfa_verified_at=datetime.now(UTC),
    )
    assert plaintext_codes, "generate_recovery_codes must return at least one code"

    first_code = plaintext_codes[0]

    # Read the raw code_hash from the DB for the first recovery code of this user.
    result = await db_session.execute(
        text(
            "SELECT code_hash FROM recovery_codes "
            "WHERE user_id = :user_id AND is_used = false "
            "LIMIT 1"
        ),
        {"user_id": user.id.hex},  # SQLite stores UUID as 32-char hex without dashes
    )
    raw_hash = result.scalar_one()

    assert raw_hash is not None, (
        "code_hash column must not be NULL after generate_recovery_codes"
    )
    assert raw_hash != first_code, (
        "Raw DB value equals the plaintext recovery code — "
        "codes are not being hashed before storage. "
        "Check that generate_recovery_codes still calls get_password_hash()."
    )
    # Argon2id hashes start with "$argon2" — verify the stored value is actually hashed.
    assert raw_hash.startswith("$argon2"), (
        f"Expected an Argon2id hash (starting with '$argon2') but got: {raw_hash[:30]!r}. "
        "Recovery codes must be stored as Argon2id hashes."
    )
