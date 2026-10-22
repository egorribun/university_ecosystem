import base64
import hashlib
import os
import secrets

import pytest
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, settings
from app.core.config.mixins.mfa_settings import MfaSettingsMixin
from app.utils.encryption import (
    SpotifyEncryptionError,
    TotpEncryptedString,
    TotpEncryptionError,
    _get_cipher,
    decrypt_string,
    decrypt_totp_string,
    encrypt_string,
    encrypt_totp_string,
    reset_cached_cipher,
    rotate_encrypted_string,
    rotate_totp_encrypted_string,
)


def test_encryption_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    original = "secret_data"
    encrypted = encrypt_string(original)
    assert encrypted != original
    decrypted = decrypt_string(encrypted)
    assert decrypted == original


def test_encryption_bytes(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    original = b"byte_data"
    encrypted = encrypt_string(original)
    decrypted = decrypt_string(encrypted)
    # decrypt returns string by default decoding utf8
    assert decrypted == "byte_data"


def test_empty_handling():
    assert encrypt_string(None) is None
    assert encrypt_string("") is None
    assert encrypt_string(b"") is None

    assert decrypt_string(None) is None
    assert decrypt_string("") is None
    assert decrypt_string(b"") is None

    assert rotate_encrypted_string(None) is None
    assert rotate_encrypted_string("") is None


def test_rotate_keys(monkeypatch):
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    # Encrypt with key2
    monkeypatch.setattr(settings, "spotify_token_secret", key2)
    reset_cached_cipher()
    cipher2 = _get_cipher()
    data = "data"
    token = cipher2.encrypt(data.encode()).decode()

    # Configure multiple keys: key1 is primary, key2 is secondary
    combined = f"{key1},{key2}"
    monkeypatch.setattr(settings, "spotify_token_secret", combined)
    reset_cached_cipher()

    # Decrypt should work (try list)
    decrypted = decrypt_string(token)
    assert decrypted == "data"

    # Rotate should re-encrypt with key1
    rotated = rotate_encrypted_string(token)
    assert rotated != token

    # Verified rotated uses key1
    f1 = Fernet(key1.encode())
    assert f1.decrypt(rotated.encode()).decode() == "data"


def test_invalid_secret_format(monkeypatch):
    monkeypatch.setattr(settings, "spotify_token_secret", "bad_key")
    reset_cached_cipher()
    with pytest.raises(SpotifyEncryptionError):
        _get_cipher()


def test_empty_secret_setting(monkeypatch):
    # If explicitly empty, should fallback to default derive
    monkeypatch.setattr(settings, "spotify_token_secret", "")
    monkeypatch.setattr(settings, "secret_key", "base_secret")
    reset_cached_cipher()

    cipher = _get_cipher()
    assert cipher


def test_no_secret_configured(monkeypatch):
    monkeypatch.setattr(settings, "spotify_token_secret", "")
    monkeypatch.setattr(settings, "secret_key", "")
    reset_cached_cipher()
    with pytest.raises(SpotifyEncryptionError):
        _get_cipher()


def test_decrypt_invalid_token(monkeypatch, caplog):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()

    import logging

    with caplog.at_level(logging.WARNING):
        res = decrypt_string("invalid_token")
        assert res is None
        assert "Failed to decrypt" in caplog.text


def test_empty_secret_entry():
    from app.utils.encryption import _normalize_secret

    with pytest.raises(SpotifyEncryptionError) as exc:
        _normalize_secret("   ")
    assert "SPOTIFY_TOKEN_SECRET contains an empty entry" in str(exc.value)


def test_decrypt_string_bytes(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    encrypted = encrypt_string("hello")
    decrypted = decrypt_string(encrypted.encode("utf-8"))
    assert decrypted == "hello"


def test_rotate_single_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    token_str = "some_token"
    token_bytes = b"some_token"
    assert rotate_encrypted_string(token_str) == "some_token"
    assert rotate_encrypted_string(token_bytes) == "some_token"


def test_encrypted_string_decorator(monkeypatch):
    from app.utils.encryption import EncryptedString

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    decorator = EncryptedString()
    encrypted = decorator.process_bind_param("hello", None)
    assert encrypted != "hello"
    decrypted = decorator.process_result_value(encrypted, None)
    assert decrypted == "hello"


def test_build_cipher_empty():
    from app.utils.encryption import _build_cipher

    with pytest.raises(SpotifyEncryptionError) as exc:
        _build_cipher("")
    assert "SPOTIFY_TOKEN_SECRET is not configured" in str(exc.value)


class _MfaEncryptionSettings(MfaSettingsMixin, BaseModel):
    environment: str = "production"
    app_process_role: str = "api"
    secret_key: str = ""
    spotify_token_secret: str = ""


def _configure_totp_keys(
    monkeypatch: pytest.MonkeyPatch,
    *,
    keyring: str,
    active_key_id: str,
) -> None:
    monkeypatch.setattr(settings.security, "mfa_totp_encryption_keys", keyring)
    monkeypatch.setattr(
        settings.security,
        "mfa_totp_active_encryption_key_id",
        active_key_id,
    )
    reset_cached_cipher()


def _fernet_key_alias(alias_kind: str) -> tuple[str, str]:
    if alias_kind == "extra-padding":
        canonical = Fernet.generate_key().decode("ascii")
        alias = f"{canonical}="
    elif alias_kind == "standard-base64":
        material = b"\xfb\xff" + bytes(range(30))
        canonical = base64.urlsafe_b64encode(material).decode("ascii")
        alias = canonical.translate(str.maketrans("-_", "+/"))
        assert "-" in canonical and "_" in canonical
    else:
        raise AssertionError(f"unsupported test alias: {alias_kind}")

    token = Fernet(alias.encode("ascii")).encrypt(b"synthetic alias fixture")
    assert (
        Fernet(canonical.encode("ascii")).decrypt(token) == b"synthetic alias fixture"
    )
    return canonical, alias


def test_totp_encrypts_with_independent_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spotify_key = Fernet.generate_key().decode("ascii")
    totp_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "spotify_token_secret", spotify_key)
    _configure_totp_keys(
        monkeypatch,
        keyring=f"active:{totp_key}",
        active_key_id="active",
    )

    token = encrypt_totp_string("totp-seed")

    assert token is not None
    assert (
        Fernet(totp_key.encode("ascii")).decrypt(token.encode("ascii")) == b"totp-seed"
    )
    with pytest.raises(InvalidToken):
        Fernet(spotify_key.encode("ascii")).decrypt(token.encode("ascii"))
    assert decrypt_totp_string(token) == "totp-seed"


def test_totp_reads_legacy_spotify_ciphertext_and_rotates_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_spotify_key = Fernet.generate_key()
    active_totp_key = Fernet.generate_key()
    legacy_token = (
        Fernet(legacy_spotify_key).encrypt(b"legacy-enrollment").decode("ascii")
    )
    monkeypatch.setattr(
        settings, "spotify_token_secret", legacy_spotify_key.decode("ascii")
    )
    _configure_totp_keys(
        monkeypatch,
        keyring=(
            f"active:{active_totp_key.decode('ascii')},"
            f"legacy:{legacy_spotify_key.decode('ascii')}"
        ),
        active_key_id="active",
    )

    assert decrypt_totp_string(legacy_token) == "legacy-enrollment"
    rotated = rotate_totp_encrypted_string(legacy_token)
    assert rotated is not None and rotated != legacy_token
    assert (
        Fernet(active_totp_key).decrypt(rotated.encode("ascii")) == b"legacy-enrollment"
    )
    assert rotate_totp_encrypted_string(rotated) == rotated


def test_totp_unknown_ciphertext_fails_closed_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_key = Fernet.generate_key()
    unknown_key = Fernet.generate_key()
    unknown_token = Fernet(unknown_key).encrypt(b"private-enrollment").decode("ascii")
    _configure_totp_keys(
        monkeypatch,
        keyring=f"active:{configured_key.decode('ascii')}",
        active_key_id="active",
    )

    with pytest.raises(TotpEncryptionError) as error:
        decrypt_totp_string(unknown_token)

    assert unknown_token not in str(error.value)
    assert "cannot be decrypted" in str(error.value)


def test_totp_encrypted_string_type_decorator_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode("ascii")
    _configure_totp_keys(monkeypatch, keyring=f"active:{key}", active_key_id="active")
    encrypted = TotpEncryptedString().process_bind_param("secret", None)

    assert encrypted is not None and encrypted != "secret"
    assert TotpEncryptedString().process_result_value(encrypted, None) == "secret"


def test_totp_encryption_rejects_non_utf8_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode("ascii")
    _configure_totp_keys(monkeypatch, keyring=f"active:{key}", active_key_id="active")

    with pytest.raises(TotpEncryptionError, match="valid UTF-8"):
        encrypt_totp_string(b"\xff")


def _generated_rs256_signing_values() -> dict[str, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return {
        "algorithm": "RS256",
        "jwt_private_key_path": None,
        "jwt_signing_keys": [f"synthetic-rs256:{private_pem}"],
        "jwt_active_kid": "synthetic-rs256",
    }


def _production_auth_settings_values(
    *, consumer: str, keyring: str, active_key_id: str
) -> dict[str, object]:
    # Migrations use the existing API process role and therefore the same
    # fail-closed TOTP requirement; workers use their explicit non-auth roles.
    role = "api" if consumer in {"api", "migrations"} else consumer
    database_password = secrets.token_urlsafe(24)
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "production",
        "app_process_role": role,
        "revocation_redis_access_enabled": role
        not in {"outbox-worker", "notifications-worker"},
        "cache_redis_url": "redis://cache.test:6379/0",
        "revocation_redis_url": "redis://revocation.test:6379/0",
        "rate_limit_storage_uri": "redis://rate-limit.test:6379/1",
        "event_file_scanner_enabled": True,
        "database_url": (
            "postgresql+asyncpg://university:"
            f"{database_password}@postgres.test:5432/totp_settings_contract"
        ),
        "secret_key": secrets.token_urlsafe(48),
        "spotify_token_secret": Fernet.generate_key().decode("ascii"),
        "spotify_client_id": "",
        "spotify_client_secret": "",
        "spotify_oauth_state_secret": "",
        "nats_auth_token": secrets.token_urlsafe(32),
        "internal_auth_token": secrets.token_urlsafe(32),
        "internal_hmac_secret": secrets.token_urlsafe(48),
        "token_hmac_secret": secrets.token_urlsafe(48),
        "audit_log_secret": secrets.token_urlsafe(48),
        "spicedb_preshared_key": secrets.token_urlsafe(32),
        "ws_hub_internal_secret": secrets.token_urlsafe(32),
        "elasticsearch_url": "https://search.test.invalid",
        "elasticsearch_password": secrets.token_urlsafe(32),
        "minio_secure": True,
        "mfa_totp_encryption_keys": keyring,
        "mfa_totp_active_encryption_key_id": active_key_id,
    }
    values.update(_generated_rs256_signing_values())
    return values


def _clear_totp_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Do not let a local .env or operator-mounted *_FILE inputs satisfy or
    # override a supposedly self-contained production contract fixture.
    for name in tuple(os.environ):
        if name.endswith("_FILE"):
            monkeypatch.delenv(name, raising=False)
    for name in (
        "APP_PROCESS_ROLE",
        "ALGORITHM",
        "DATABASE_URL",
        "ELASTICSEARCH_PASSWORD",
        "ENVIRONMENT",
        "INTERNAL_AUTH_TOKEN",
        "INTERNAL_HMAC_SECRET",
        "JWT_ACTIVE_KID",
        "JWT_PRIVATE_KEY_PATH",
        "JWT_SIGNING_KEYS",
        "MFA_TOTP_ENCRYPTION_KEYS",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "NATS_AUTH_TOKEN",
        "SECRET_KEY",
        "SPOTIFY_TOKEN_SECRET",
        "TOKEN_HMAC_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")


@pytest.mark.parametrize("consumer", ("api", "migrations"))
def test_full_production_settings_require_totp_ring_for_auth_consumers(
    consumer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_totp_settings_environment(monkeypatch)

    active_key = Fernet.generate_key().decode("ascii")
    configured = Settings(
        **_production_auth_settings_values(
            consumer=consumer,
            keyring=f"active:{active_key}",
            active_key_id="active",
        )
    )
    assert configured.environment == "production"
    assert configured.app_process_role == "api"
    assert configured.mfa_totp_active_encryption_key_id == "active"
    assert active_key not in repr(configured)

    with pytest.raises(ValidationError, match="MFA_TOTP_ENCRYPTION_KEYS"):
        Settings(
            **_production_auth_settings_values(
                consumer=consumer, keyring="", active_key_id=""
            )
        )


def test_full_production_settings_hide_invalid_totp_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_totp_settings_environment(monkeypatch)

    sentinel = "synthetic-invalid-totp-key-material"
    with pytest.raises(ValidationError) as error:
        Settings(
            **_production_auth_settings_values(
                consumer="api",
                keyring=f"active:{sentinel}",
                active_key_id="active",
            )
        )

    assert sentinel not in str(error.value)
    assert sentinel not in repr(error.value)


def test_production_mfa_settings_require_explicit_totp_ring() -> None:
    with pytest.raises(ValidationError, match="MFA_TOTP_ENCRYPTION_KEYS"):
        _MfaEncryptionSettings(environment="production", app_process_role="api")


@pytest.mark.parametrize("role", ("outbox-worker", "notifications-worker"))
def test_non_auth_worker_settings_start_without_totp_keys(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_totp_settings_environment(monkeypatch)

    configured = Settings(
        **_production_auth_settings_values(consumer=role, keyring="", active_key_id="")
    )

    assert configured.app_process_role == role
    assert configured.revocation_redis_access_enabled is False
    assert configured.mfa_totp_encryption_keys == ""
    assert configured.mfa_totp_active_encryption_key_id == ""


@pytest.mark.parametrize("role", ("outbox-worker", "notifications-worker"))
def test_keyless_production_worker_totp_crypto_fails_closed(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "app_process_role", role)
    monkeypatch.setattr(settings, "secret_key", secrets.token_urlsafe(32))
    _configure_totp_keys(monkeypatch, keyring="", active_key_id="")

    with pytest.raises(TotpEncryptionError, match="required outside development"):
        encrypt_totp_string("private-enrollment")


def test_active_totp_key_must_not_be_a_spotify_key() -> None:
    key = Fernet.generate_key().decode("ascii")

    with pytest.raises(ValidationError, match="independent of SPOTIFY_TOKEN_SECRET"):
        _MfaEncryptionSettings(
            environment="production",
            spotify_token_secret=key,
            mfa_totp_encryption_keys=f"active:{key}",
            mfa_totp_active_encryption_key_id="active",
        )


@pytest.mark.parametrize("alias_kind", ("extra-padding", "standard-base64"))
def test_full_production_settings_reject_spotify_key_encoding_alias(
    alias_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_totp_settings_environment(monkeypatch)
    active_key, spotify_alias = _fernet_key_alias(alias_kind)
    values = _production_auth_settings_values(
        consumer="api",
        keyring=f"active:{active_key}",
        active_key_id="active",
    )
    values["spotify_token_secret"] = spotify_alias

    with pytest.raises(ValidationError, match="independent of SPOTIFY_TOKEN_SECRET"):
        Settings(**values)


@pytest.mark.parametrize("alias_kind", ("extra-padding", "standard-base64"))
def test_full_production_settings_reject_duplicate_totp_ring_alias(
    alias_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_totp_settings_environment(monkeypatch)
    key, key_alias = _fernet_key_alias(alias_kind)
    values = _production_auth_settings_values(
        consumer="api",
        keyring=f"active:{key},legacy:{key_alias}",
        active_key_id="active",
    )

    with pytest.raises(ValidationError, match="unique keys"):
        Settings(**values)


def test_full_production_settings_reject_totp_alias_of_spotify_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_totp_settings_environment(monkeypatch)
    secret_key = secrets.token_urlsafe(32)
    fallback_key = base64.urlsafe_b64encode(
        hashlib.sha256(secret_key.encode("utf-8")).digest()
    ).decode("ascii")
    active_alias = f"{fallback_key}="
    values = _production_auth_settings_values(
        consumer="api",
        keyring=f"active:{active_alias}",
        active_key_id="active",
    )
    values["secret_key"] = secret_key

    with pytest.raises(ValidationError, match="independent of SPOTIFY_TOKEN_SECRET"):
        Settings(**values)


def test_totp_runtime_rechecks_active_key_after_explicit_spotify_secret_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = Fernet.generate_key().decode("ascii")
    other_spotify_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings.app, "environment", "production")
    monkeypatch.setattr(settings.security, "secret_key", secrets.token_urlsafe(32))
    monkeypatch.setattr(
        settings.integrations, "spotify_token_secret", other_spotify_key
    )
    _configure_totp_keys(
        monkeypatch, keyring=f"active:{active_key}", active_key_id="active"
    )

    stored = encrypt_totp_string("private-enrollment")
    assert stored is not None

    # Settings is a live composed object and can be reloaded or changed after its
    # initial model validation. Crypto helpers must enforce the same invariant.
    monkeypatch.setattr(settings.integrations, "spotify_token_secret", active_key)
    for operation in (
        lambda: encrypt_totp_string("new-enrollment"),
        lambda: decrypt_totp_string(stored),
    ):
        with pytest.raises(TotpEncryptionError, match="independent") as error:
            operation()
        assert active_key not in str(error.value)
        assert other_spotify_key not in str(error.value)


@pytest.mark.parametrize("alias_kind", ("extra-padding", "standard-base64"))
def test_totp_runtime_rechecks_spotify_key_alias_after_cipher_cache(
    alias_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key, spotify_alias = _fernet_key_alias(alias_kind)
    other_spotify_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings.app, "environment", "production")
    monkeypatch.setattr(settings.security, "secret_key", secrets.token_urlsafe(32))
    monkeypatch.setattr(
        settings.integrations, "spotify_token_secret", other_spotify_key
    )
    _configure_totp_keys(
        monkeypatch, keyring=f"active:{active_key}", active_key_id="active"
    )

    stored = encrypt_totp_string("private-enrollment")
    assert stored is not None
    monkeypatch.setattr(settings.integrations, "spotify_token_secret", spotify_alias)

    for operation in (
        lambda: encrypt_totp_string("new-enrollment"),
        lambda: decrypt_totp_string(stored),
    ):
        with pytest.raises(TotpEncryptionError, match="independent") as error:
            operation()
        assert active_key not in str(error.value)
        assert spotify_alias not in str(error.value)


@pytest.mark.parametrize("alias_kind", ("extra-padding", "standard-base64"))
def test_totp_runtime_rejects_duplicate_ring_alias_after_settings_mutation(
    alias_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key, key_alias = _fernet_key_alias(alias_kind)
    monkeypatch.setattr(settings.app, "environment", "production")
    monkeypatch.setattr(settings.security, "secret_key", secrets.token_urlsafe(32))
    monkeypatch.setattr(
        settings.integrations,
        "spotify_token_secret",
        Fernet.generate_key().decode("ascii"),
    )
    _configure_totp_keys(monkeypatch, keyring=f"active:{key}", active_key_id="active")

    stored = encrypt_totp_string("private-enrollment")
    assert stored is not None
    monkeypatch.setattr(
        settings.security,
        "mfa_totp_encryption_keys",
        f"active:{key},legacy:{key_alias}",
    )

    with pytest.raises(TotpEncryptionError, match="duplicate keys"):
        decrypt_totp_string(stored)


def test_totp_runtime_rechecks_secret_key_fallback_after_secret_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacement_secret = secrets.token_urlsafe(32)
    active_key = (
        base64.urlsafe_b64encode(
            hashlib.sha256(replacement_secret.encode("utf-8")).digest()
        ).decode("ascii")
        + "="
    )
    spotify_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings.app, "environment", "production")
    monkeypatch.setattr(settings.security, "secret_key", secrets.token_urlsafe(32))
    monkeypatch.setattr(settings.integrations, "spotify_token_secret", spotify_key)
    _configure_totp_keys(
        monkeypatch, keyring=f"active:{active_key}", active_key_id="active"
    )

    stored = encrypt_totp_string("private-enrollment")
    assert stored is not None
    monkeypatch.setattr(settings.security, "secret_key", replacement_secret)

    with pytest.raises(TotpEncryptionError, match="independent") as error:
        encrypt_totp_string("new-enrollment")
    assert active_key not in str(error.value)
    assert replacement_secret not in str(error.value)
    assert spotify_key not in str(error.value)


def test_active_totp_key_must_not_match_spotify_secret_key_fallback() -> None:
    secret_key = secrets.token_urlsafe(32)
    spotify_fallback_key = base64.urlsafe_b64encode(
        hashlib.sha256(secret_key.encode("utf-8")).digest()
    ).decode("ascii")

    with pytest.raises(ValidationError, match="independent of SPOTIFY_TOKEN_SECRET"):
        _MfaEncryptionSettings(
            environment="staging",
            secret_key=secret_key,
            spotify_token_secret="",
            mfa_totp_encryption_keys=f"active:{spotify_fallback_key}",
            mfa_totp_active_encryption_key_id="active",
        )


def test_active_totp_key_must_not_match_fallback_when_explicit_spotify_key_is_set() -> (
    None
):
    secret_key = secrets.token_urlsafe(32)
    explicit_spotify_key = Fernet.generate_key().decode("ascii")
    spotify_fallback_key = base64.urlsafe_b64encode(
        hashlib.sha256(secret_key.encode("utf-8")).digest()
    ).decode("ascii")

    with pytest.raises(ValidationError, match="independent of SPOTIFY_TOKEN_SECRET"):
        _MfaEncryptionSettings(
            environment="production",
            secret_key=secret_key,
            spotify_token_secret=explicit_spotify_key,
            mfa_totp_encryption_keys=f"active:{spotify_fallback_key}",
            mfa_totp_active_encryption_key_id="active",
        )


def test_spotify_key_is_allowed_only_as_an_explicit_legacy_totp_key() -> None:
    legacy_key = Fernet.generate_key().decode("ascii")
    active_key = Fernet.generate_key().decode("ascii")

    configured = _MfaEncryptionSettings(
        environment="production",
        spotify_token_secret=legacy_key,
        mfa_totp_encryption_keys=f"active:{active_key},legacy:{legacy_key}",
        mfa_totp_active_encryption_key_id="active",
    )

    assert configured.mfa_totp_active_encryption_key_id == "active"
    assert configured.mfa_totp_encryption_keys.endswith(f"legacy:{legacy_key}")
