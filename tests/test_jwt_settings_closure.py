from __future__ import annotations

import pytest

from app.core.config.mixins.jwt_settings import JwtSettingsMixin
from app.core.config.security import SecuritySettings


def _development_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", "s" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_SIGNING_KEYS", "")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")


def _production_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("AUDIT_LOG_SECRET", "a" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "i" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")


def test_signing_key_entropy_accepts_non_key_entry_without_colon(monkeypatch):
    _production_env(monkeypatch)
    monkeypatch.setenv("JWT_SIGNING_KEYS", "plain-entry-without-colon")
    settings = SecuritySettings()
    assert settings.jwt_signing_keys == "plain-entry-without-colon"


def test_algorithm_validator_normalizes_unrecognized_algorithm(monkeypatch):
    _development_env(monkeypatch)
    monkeypatch.setenv("ALGORITHM", "eddsa")
    settings = SecuritySettings()
    assert settings.algorithm == "EDDSA"


def test_production_placeholder_audience_logs_warning(monkeypatch, caplog):
    _production_env(monkeypatch)
    monkeypatch.setenv("JWT_AUDIENCE", "api")
    settings = SecuritySettings()
    assert settings.jwt_audience == "api"
    assert "generic placeholder" in caplog.text


def test_rs256_private_key_missing_falls_back_only_in_development(monkeypatch):
    _development_env(monkeypatch)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "app/core/config/mixins/jwt_settings.py")
    loaded = SecuritySettings()
    assert loaded.jwt_signing_key_registry["primary"]

    _development_env(monkeypatch)
    monkeypatch.setenv(
        "JWT_PRIVATE_KEY_PATH", "C:\\missing\\jwt-private-key.pem"
    )  # pragma: allowlist secret
    settings = SecuritySettings()
    assert settings.jwt_signing_key_registry == {"primary": settings.secret_key}

    dummy = type(
        "JwtConfig",
        (JwtSettingsMixin,),
        {
            "jwt_signing_keys": "",
            "jwt_active_kid": None,
            "algorithm": "RS256",
            "jwt_private_key_path": "C:\\missing\\jwt-private-key.pem",  # pragma: allowlist secret
            "secret_key": "s" * 48,  # pragma: allowlist secret
            "environment": "production",
        },
    )()
    with pytest.raises(RuntimeError, match="Failed to load JWT_PRIVATE_KEY_PATH"):
        dummy._build_jwt_signing_key_entries()


def test_active_secret_fails_closed_when_registry_has_no_secret(monkeypatch):
    _development_env(monkeypatch)
    settings = SecuritySettings()

    class _Registry(dict):
        def get(self, key, default=None):
            return None

    monkeypatch.setattr(
        type(settings),
        "jwt_signing_key_registry",
        property(lambda _self: _Registry({"primary": "secret"})),
    )
    settings.jwt_active_kid = "primary"
    with pytest.raises(RuntimeError, match="does not contain the active kid"):
        _ = settings.jwt_signing_active_secret
