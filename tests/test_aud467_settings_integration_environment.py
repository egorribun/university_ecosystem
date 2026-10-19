"""AUD-467/AUD-471 regressions for composed integration and SMTP settings."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI

import app.core.lifespan as lifecycle
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
        "smtp_host": "relay.aud471.invalid",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_user": "",
        "smtp_password": "",
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
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SECURITY",
        "SMTP_STARTTLS",
        "SMTP_USER",
        "SMTP_PASSWORD",
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


@pytest.mark.parametrize("environment", ("production", "staging"))
def test_full_settings_accepts_complete_non_development_configuration(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All production settings validate when only the ES password is supplied."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
    _clear_secret_file_inputs(monkeypatch)

    settings_inputs = _valid_production_settings()
    settings_inputs["elasticsearch_password"] = secrets.token_urlsafe(32)
    settings_inputs["_env_file"] = None

    settings = Settings(**settings_inputs)

    assert settings.environment == environment
    assert settings.algorithm == "RS256"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.elasticsearch_password == settings_inputs["elasticsearch_password"]
    assert settings.smtp_host == "relay.aud471.invalid"
    assert settings.smtp_port == 587
    assert settings.smtp_security == "starttls"
    assert settings.smtp_user == ""
    assert settings.smtp_password == ""


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
    assert settings.smtp_host == ""
    assert settings.smtp_port == 0

    mailpit = Settings(
        environment=environment,
        database_url="sqlite+aiosqlite:///./aud467-settings-local.db",
        secret_key=secrets.token_urlsafe(48),
        elasticsearch_password="",
        smtp_host="127.0.0.1",
        smtp_port=1025,
        smtp_security="none",
        _env_file=None,
    )
    assert mailpit.smtp_host == "127.0.0.1"
    assert mailpit.smtp_port == 1025
    assert mailpit.smtp_security == "none"


def _api_smtp_settings_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    _clear_secret_file_inputs(monkeypatch)
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    values = _valid_production_settings()
    values.update(
        elasticsearch_password=secrets.token_urlsafe(32),
        app_process_role="api",
        revocation_redis_access_enabled=True,
        _env_file=None,
    )
    return values


def _settings_with_smtp_source(
    source: str,
    *,
    environment: str,
    smtp_values: dict[str, str | int],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Settings:
    values = _api_smtp_settings_inputs(monkeypatch)
    for field in ("smtp_host", "smtp_port", "smtp_security"):
        values.pop(field)

    if source == "process":
        monkeypatch.setenv("ENVIRONMENT", environment)
        for name, value in smtp_values.items():
            monkeypatch.setenv(name, str(value))
    elif source == "constructor":
        monkeypatch.setenv("ENVIRONMENT", "testing")
        values["environment"] = environment
        values.update({name.lower(): value for name, value in smtp_values.items()})
    elif source == "dotenv":
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        env_file = tmp_path / "smtp.env"
        lines = [f"ENVIRONMENT={environment}"]
        lines.extend(f"{name}={value}" for name, value in smtp_values.items())
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        values["_env_file"] = env_file
    else:
        raise AssertionError(f"unexpected settings source: {source}")

    return Settings(**values)


@pytest.mark.parametrize(
    ("source", "expected_host", "expected_port", "expected_security"),
    [
        ("constructor", "constructor.aud471.invalid", 587, "starttls"),
        ("process", "process.aud471.invalid", 465, "ssl"),
        ("dotenv", "dotenv.aud471.invalid", 2525, "starttls"),
    ],
)
def test_full_settings_preserves_smtp_settings_source_precedence(
    source: str,
    expected_host: str,
    expected_port: int,
    expected_security: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = _api_smtp_settings_inputs(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("SMTP_HOST", "process.aud471.invalid")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    dotenv = tmp_path / "smtp-precedence.env"
    dotenv.write_text(
        "SMTP_HOST=dotenv.aud471.invalid\nSMTP_PORT=2525\nSMTP_SECURITY=starttls\n",
        encoding="utf-8",
    )
    values["environment"] = "production"
    values["_env_file"] = dotenv
    if source == "constructor":
        values.update(
            smtp_host="constructor.aud471.invalid",
            smtp_port=587,
            smtp_security="starttls",
        )
    else:
        for field in ("smtp_host", "smtp_port", "smtp_security"):
            values.pop(field)
        if source == "dotenv":
            for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY"):
                monkeypatch.delenv(name, raising=False)

    settings = Settings(**values)

    assert settings.smtp_host == expected_host
    assert settings.smtp_port == expected_port
    assert settings.smtp_security == expected_security
    assert settings.smtp_user == ""
    assert settings.smtp_password == ""


@pytest.mark.parametrize("environment_source", ("process", "constructor", "dotenv"))
@pytest.mark.parametrize("environment", ("production", "staging"))
@pytest.mark.parametrize(
    ("smtp_values", "expected_error"),
    [
        pytest.param(
            {"SMTP_HOST": "", "SMTP_PORT": 587, "SMTP_SECURITY": "starttls"},
            "SMTP_HOST",
            id="missing-host",
        ),
        pytest.param(
            {
                "SMTP_HOST": "relay.aud471.invalid",
                "SMTP_PORT": 0,
                "SMTP_SECURITY": "starttls",
            },
            "SMTP_PORT",
            id="missing-port",
        ),
    ],
)
def test_non_development_api_requires_smtp_from_composed_settings_source(
    environment_source: str,
    environment: str,
    smtp_values: dict[str, str | int],
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        _settings_with_smtp_source(
            environment_source,
            environment=environment,
            smtp_values=smtp_values,
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
        )


@pytest.mark.parametrize(
    ("smtp_values", "expected_error"),
    [
        pytest.param(
            {"SMTP_HOST": "   ", "SMTP_PORT": 587, "SMTP_SECURITY": "starttls"},
            "SMTP_HOST",
            id="whitespace-host",
        ),
        pytest.param(
            {
                "SMTP_HOST": "relay.aud471.invalid",
                "SMTP_PORT": -1,
                "SMTP_SECURITY": "starttls",
            },
            "SMTP_PORT",
            id="negative-port",
        ),
        pytest.param(
            {
                "SMTP_HOST": "relay.aud471.invalid",
                "SMTP_PORT": 65536,
                "SMTP_SECURITY": "starttls",
            },
            "SMTP_PORT",
            id="port-too-large",
        ),
    ],
)
def test_non_development_api_rejects_invalid_smtp_host_and_port(
    smtp_values: dict[str, str | int],
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        _settings_with_smtp_source(
            "constructor",
            environment="production",
            smtp_values=smtp_values,
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
        )


@pytest.mark.parametrize(
    ("role", "smtp_host", "smtp_port", "smtp_security"),
    [
        ("outbox-worker", "relay.aud471.invalid", 587, "starttls"),
        ("notifications-worker", "", 0, "none"),
    ],
)
def test_api_reset_smtp_requirement_preserves_worker_role_scope(
    role: str,
    smtp_host: str,
    smtp_port: int,
    smtp_security: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Outbox MFA is an SMTP consumer and receives a relay, not an exemption
    # claiming that an unconfigured outbox can successfully deliver MFA email.
    values = _api_smtp_settings_inputs(monkeypatch)
    values.update(
        environment="production",
        app_process_role=role,
        revocation_redis_access_enabled=False,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_security=smtp_security,
    )
    settings = Settings(**values)

    assert settings.app_process_role == role
    assert settings.smtp_host == smtp_host
    assert settings.smtp_port == smtp_port


@pytest.mark.parametrize("smtp_port", [1, 65535])
def test_non_development_api_accepts_smtp_port_boundaries(
    smtp_port: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings_with_smtp_source(
        "constructor",
        environment="production",
        smtp_values={
            "SMTP_HOST": "relay.aud471.invalid",
            "SMTP_PORT": smtp_port,
            "SMTP_SECURITY": "starttls",
        },
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )
    assert settings.smtp_port == smtp_port


def test_composed_non_development_api_rejects_plaintext_anonymous_smtp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="SMTP_SECURITY"):
        _settings_with_smtp_source(
            "constructor",
            environment="production",
            smtp_values={
                "SMTP_HOST": "relay.aud471.invalid",
                "SMTP_PORT": 587,
                "SMTP_SECURITY": "none",
            },
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
        )


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_shared_settings_can_load_without_starting_api_email_delivery(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _api_smtp_settings_inputs(monkeypatch)
    values.update(
        environment=environment,
        smtp_host="",
        smtp_port=0,
        smtp_security="none",
    )

    configured = Settings(**values)

    assert configured.app_process_role == "api"
    assert configured.revocation_redis_access_enabled is True
    assert configured.smtp_host == ""
    assert configured.smtp_port == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize("role", ["api", "outbox-worker", "notifications-worker"])
@pytest.mark.parametrize(
    ("smtp_host", "smtp_port", "expected_error"),
    [("", 587, "SMTP_HOST"), ("relay.aud471.invalid", 0, "SMTP_PORT")],
)
async def test_api_lifespan_rejects_missing_smtp_before_resources(
    environment: str,
    role: str,
    smtp_host: str,
    smtp_port: int,
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = SimpleNamespace(
        environment=environment,
        app_process_role=role,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_security="starttls",
        embedded_cdc_outbox_worker_enabled=False,
    )
    reset = Mock()
    startup = AsyncMock(
        side_effect=AssertionError("API resources reached before SMTP validation")
    )
    scheduler_stop = SimpleNamespace(clear=Mock())
    monkeypatch.setattr(lifecycle, "settings", configured)
    monkeypatch.setattr(lifecycle, "_SCHEDULER_STOP", scheduler_stop)
    monkeypatch.setattr(lifecycle, "_reset_closed_dishka_container", reset)
    monkeypatch.setattr(lifecycle, "_startup_database_and_di", startup)

    with pytest.raises(ValueError, match=expected_error):
        async with lifecycle.lifespan(FastAPI()):
            pytest.fail("invalid API email configuration must not serve requests")

    scheduler_stop.clear.assert_not_called()
    reset.assert_not_called()
    startup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "smtp_host", "smtp_port"),
    [
        ("production", "relay.aud471.invalid", 587),
        ("staging", "relay.aud471.invalid", 465),
        ("development", "", 0),
        ("testing", "", 0),
        ("local", "", 0),
        ("dev", "", 0),
        ("test", "", 0),
    ],
)
async def test_api_lifespan_allows_configured_relay_and_development_defaults(
    environment: str,
    smtp_host: str,
    smtp_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = SimpleNamespace(
        environment=environment,
        app_process_role="api",
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_security="starttls" if smtp_host else "none",
        embedded_cdc_outbox_worker_enabled=False,
    )
    app = FastAPI()
    reset = Mock()
    startup = AsyncMock(side_effect=RuntimeError("api startup reached"))
    scheduler_stop = SimpleNamespace(clear=Mock())
    monkeypatch.setattr(lifecycle, "settings", configured)
    monkeypatch.setattr(lifecycle, "_SCHEDULER_STOP", scheduler_stop)
    monkeypatch.setattr(lifecycle, "_reset_closed_dishka_container", reset)
    monkeypatch.setattr(lifecycle, "_startup_database_and_di", startup)

    with pytest.raises(RuntimeError, match=r"^api startup reached$"):
        async with lifecycle.lifespan(app):
            pytest.fail("startup sentinel must stop before later resources")

    scheduler_stop.clear.assert_called_once_with()
    reset.assert_called_once_with(app)
    startup.assert_awaited_once_with(app)
