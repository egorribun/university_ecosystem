"""AUD-467 regressions for environment-aware integration settings."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings


def _valid_production_settings() -> dict[str, object]:
    """Build a fully valid synthetic production config except ES password."""
    secret_key = secrets.token_urlsafe(48)
    spotify_key = Fernet.generate_key().decode("ascii")
    spotify_material = base64.urlsafe_b64decode(spotify_key.encode("ascii"))
    fallback_material = hashlib.sha256(secret_key.encode("utf-8")).digest()
    totp_key = Fernet.generate_key().decode("ascii")
    while base64.urlsafe_b64decode(totp_key.encode("ascii")) in {
        spotify_material,
        fallback_material,
    }:
        totp_key = Fernet.generate_key().decode("ascii")

    database_password = secrets.token_urlsafe(24)

    values: dict[str, object] = {
        "database_url": (
            "postgresql+asyncpg://university:"
            f"{database_password}@pgbouncer:5432/aud467_settings_contract"
        ),
        "secret_key": secret_key,
        "spotify_token_secret": spotify_key,
        "nats_auth_token": secrets.token_urlsafe(32),
        "mfa_totp_encryption_keys": f"active:{totp_key}",
        "mfa_totp_active_encryption_key_id": "active",
        "audit_log_secret": secrets.token_urlsafe(48),
        "token_hmac_secret": secrets.token_urlsafe(48),
        "internal_hmac_secret": secrets.token_urlsafe(48),
        "internal_auth_token": secrets.token_urlsafe(32),
        "spicedb_preshared_key": secrets.token_urlsafe(32),
        "ws_hub_internal_secret": secrets.token_urlsafe(32),
        "cache_redis_url": "redis://cache.aud467.invalid:6379/0",
        "revocation_redis_url": "redis://revocation.aud467.invalid:6379/0",
        "event_file_scanner_enabled": True,
        "event_file_scanner_host": "clamd.aud467.invalid",
        "minio_secure": True,
        "elasticsearch_url": "https://search.aud467.invalid",
        "elasticsearch_password": "",
    }
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    values.update(
        {
            "algorithm": "RS256",
            "jwt_private_key_path": None,
            "jwt_signing_keys": [f"synthetic-rs256:{private_pem}"],
            "jwt_active_kid": "synthetic-rs256",
        }
    )
    return values


def _clear_secret_file_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these config tests independent from any operator-mounted secrets."""
    for name in tuple(os.environ):
        if name.endswith("_FILE"):
            monkeypatch.delenv(name, raising=False)
    for name in (
        "ALGORITHM",
        "JWT_ACTIVE_KID",
        "JWT_PRIVATE_KEY_PATH",
        "JWT_SIGNING_KEYS",
        "AUDIT_LOG_SECRET_FILE",
        "CACHE_REDIS_URL_FILE",
        "CSRF_HMAC_SECRET_FILE",
        "CWV_MANUAL_TESTER_USER_IDS_FILE",
        "CWV_RUM_SIGNING_SECRET_FILE",
        "DATABASE_URL_FILE",
        "ELASTICSEARCH_PASSWORD_FILE",
        "IDEMPOTENCY_HMAC_SECRET_FILE",
        "INTERNAL_AUTH_TOKEN_FILE",
        "INTERNAL_HMAC_SECRET_FILE",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID_FILE",
        "MFA_EMAIL_DELIVERY_KEKS_FILE",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID_FILE",
        "MFA_EMAIL_OTP_HMAC_KEYS_FILE",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE",
        "MFA_TOTP_ENCRYPTION_KEYS_FILE",
        "MFA_TOTP_ENCRYPTION_KEYS",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID_FILE",
        "MFA_TRUSTED_DEVICE_HMAC_KEYS_FILE",
        "NATS_AUTH_TOKEN_FILE",
        "NATS_URL_FILE",
        "RATE_LIMIT_STORAGE_URI_FILE",
        "REVOCATION_REDIS_URL_FILE",
        "SECRET_KEY_FILE",
        "SMTP_PASSWORD_FILE",
        "SPICEDB_PRESHARED_KEY_FILE",
        "SPOTIFY_CLIENT_SECRET_FILE",
        "SPOTIFY_OAUTH_STATE_SECRET_FILE",
        "SPOTIFY_TOKEN_SECRET_FILE",
        "STORAGE_S3_ACCESS_KEY_ID_FILE",
        "STORAGE_S3_SECRET_ACCESS_KEY_FILE",
        "TOKEN_HMAC_SECRET_FILE",
        "VAPID_PRIVATE_KEY_FILE",
        "WS_HUB_INTERNAL_SECRET_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("environment_source", ("process", "constructor", "dotenv"))
def test_full_settings_enforces_production_integration_secrets_from_environment(
    environment_source: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Production policy follows the composed Settings environment field."""
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
    _clear_secret_file_inputs(monkeypatch)

    settings_inputs = _valid_production_settings()
    if environment_source == "process":
        monkeypatch.setenv("ENVIRONMENT", "production")
        settings_inputs["_env_file"] = None
    elif environment_source == "constructor":
        monkeypatch.setenv("ENVIRONMENT", "testing")
        settings_inputs["_env_file"] = None
        settings_inputs["environment"] = "production"
    else:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        env_file = tmp_path / "production.env"
        env_file.write_text("ENVIRONMENT=production\n", encoding="utf-8")
        settings_inputs["_env_file"] = env_file

    with pytest.raises(ValueError, match="ELASTICSEARCH_PASSWORD is required"):
        Settings(**settings_inputs)


def test_full_settings_accepts_complete_production_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All production settings validate when only the ES password is supplied."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
    _clear_secret_file_inputs(monkeypatch)

    settings_inputs = _valid_production_settings()
    settings_inputs["elasticsearch_password"] = secrets.token_urlsafe(32)
    settings_inputs["_env_file"] = None

    settings = Settings(**settings_inputs)

    assert settings.environment == "production"
    assert settings.algorithm == "RS256"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.elasticsearch_password == settings_inputs["elasticsearch_password"]


@pytest.mark.parametrize("environment", ("development", "testing"))
def test_full_settings_preserves_development_and_test_integration_behavior(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The normal development and test environments remain exempt."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
    _clear_secret_file_inputs(monkeypatch)

    settings = Settings(
        environment=environment,
        database_url="sqlite+aiosqlite:///./aud467-settings-local.db",
        secret_key=secrets.token_urlsafe(48),
        elasticsearch_password="",
        _env_file=None,
    )

    assert settings.environment == environment
    assert settings.integrations.environment == environment
