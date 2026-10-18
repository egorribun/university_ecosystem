import secrets
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.utils.encryption import (
    TotpEncryptionError,
    _ensure_totp_active_key_independent,
    decrypt_totp_string,
    encrypt_totp_string,
    reset_cached_cipher,
    rotate_totp_encrypted_string,
)


@pytest.fixture(autouse=True)
def _reset_cipher_cache() -> Iterator[None]:
    reset_cached_cipher()
    yield
    reset_cached_cipher()


def _configure_totp(
    monkeypatch: pytest.MonkeyPatch,
    *,
    keyring: str,
    active_key_id: str,
    environment: str = "production",
    secret_key: str | None = None,
    spotify_secret: str = "",
) -> None:
    if secret_key is None:
        secret_key = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings.app, "environment", environment)
    monkeypatch.setattr(settings.security, "secret_key", secret_key)
    monkeypatch.setattr(settings.security, "mfa_totp_encryption_keys", keyring)
    monkeypatch.setattr(
        settings.security, "mfa_totp_active_encryption_key_id", active_key_id
    )
    monkeypatch.setattr(settings.integrations, "spotify_token_secret", spotify_secret)
    reset_cached_cipher()


def test_development_fallback_fails_closed_without_primary_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_totp(
        monkeypatch,
        keyring="",
        active_key_id="",
        environment="development",
        secret_key="",
    )

    with pytest.raises(
        TotpEncryptionError, match="MFA_TOTP_ENCRYPTION_KEYS is not configured"
    ):
        encrypt_totp_string("synthetic-enrollment")


def test_missing_active_key_guard_rejects_ring_without_disclosing_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_key = Fernet.generate_key().decode("ascii")
    _configure_totp(
        monkeypatch,
        keyring=f"legacy:{legacy_key}",
        active_key_id="active",
    )

    with pytest.raises(
        TotpEncryptionError, match="Invalid MFA TOTP encryption"
    ) as error:
        _ensure_totp_active_key_independent(f"legacy:{legacy_key}", "active")

    assert legacy_key not in str(error.value)


def test_runtime_keyring_errors_are_domain_errors_without_key_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_key = "κey-material"
    cases = (
        ("active", "active", "unique key-id"),
        (f"active:{invalid_key}", "active", "invalid Fernet key"),
        (
            f"legacy:{Fernet.generate_key().decode('ascii')}",
            "active",
            "does not identify",
        ),
    )

    for keyring, active_key_id, expected_message in cases:
        _configure_totp(monkeypatch, keyring=keyring, active_key_id=active_key_id)

        with pytest.raises(TotpEncryptionError, match=expected_message) as error:
            encrypt_totp_string("synthetic-enrollment")

        assert invalid_key not in str(error.value)


def test_invalid_live_spotify_key_is_sanitized_after_cipher_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    spotify_key = Fernet.generate_key().decode("ascii")
    invalid_live_value = "synthetic-invalid-spotify-key"
    _configure_totp(
        monkeypatch,
        keyring=f"active:{active_key}",
        active_key_id="active",
        spotify_secret=spotify_key,
    )

    original = encrypt_totp_string("synthetic-enrollment")
    assert original is not None

    # The Fernet cipher is cached by keyring, but composed settings are rechecked
    # on every operation before that cached cipher can be used.
    monkeypatch.setattr(
        settings.integrations, "spotify_token_secret", invalid_live_value
    )
    with pytest.raises(
        TotpEncryptionError, match="Invalid MFA TOTP encryption configuration"
    ) as error:
        encrypt_totp_string("synthetic-next-enrollment")

    assert invalid_live_value not in str(error.value)
    assert error.value.__cause__ is None


def test_explicit_keyring_works_without_spotify_fallback_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    spotify_key = Fernet.generate_key().decode("ascii")
    _configure_totp(
        monkeypatch,
        keyring=f"active:{active_key}",
        active_key_id="active",
        secret_key="",
        spotify_secret=spotify_key,
    )

    token = encrypt_totp_string("synthetic-enrollment")

    assert token is not None
    assert Fernet(active_key.encode("ascii")).decrypt(token.encode("ascii")) == (
        b"synthetic-enrollment"
    )
    assert decrypt_totp_string(token) == "synthetic-enrollment"


def test_legacy_key_before_active_key_remains_readable_and_rotates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_key = Fernet.generate_key()
    active_key = Fernet.generate_key()
    legacy_token = Fernet(legacy_key).encrypt(b"synthetic-legacy-seed").decode("ascii")
    _configure_totp(
        monkeypatch,
        keyring=(
            f"legacy:{legacy_key.decode('ascii')},active:{active_key.decode('ascii')}"
        ),
        active_key_id="active",
        spotify_secret=legacy_key.decode("ascii"),
    )

    assert decrypt_totp_string(legacy_token) == "synthetic-legacy-seed"
    rotated = rotate_totp_encrypted_string(legacy_token)

    assert rotated is not None and rotated != legacy_token
    assert Fernet(active_key).decrypt(rotated.encode("ascii")) == (
        b"synthetic-legacy-seed"
    )
    assert rotate_totp_encrypted_string(rotated) == rotated


def test_totp_empty_inputs_normalize_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    _configure_totp(
        monkeypatch,
        keyring=f"active:{active_key}",
        active_key_id="active",
    )

    for value in (None, "", b""):
        assert encrypt_totp_string(value) is None
        assert decrypt_totp_string(value) is None
        assert rotate_totp_encrypted_string(value) is None
