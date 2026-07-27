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


def _mixin(**values: object) -> JwtSettingsMixin:
    instance = object.__new__(JwtSettingsMixin)
    instance.__dict__.update(values)
    return instance


def test_jwt_validators_reject_empty_and_short_production_values(monkeypatch):
    _development_env(monkeypatch)
    with pytest.raises(ValueError, match="must not be empty"):
        SecuritySettings(secret_key="")

    _production_env(monkeypatch)
    with pytest.raises(ValueError, match="at least 32 characters"):
        SecuritySettings(secret_key="s" * 31)

    with pytest.raises(ValueError, match="JWT_SIGNING_KEYS entries"):
        SecuritySettings(jwt_signing_keys="kid:short")

    accepted = SecuritySettings(jwt_signing_keys="kid:" + "s" * 32)
    assert accepted.jwt_signing_keys == "kid:" + "s" * 32
    pem = SecuritySettings(jwt_signing_keys="kid:-----BEGIN PRIVATE KEY-----")
    assert pem.jwt_signing_keys == "kid:-----BEGIN PRIVATE KEY-----"

    _development_env(monkeypatch)
    local_short = SecuritySettings(jwt_signing_keys="kid:short")
    assert local_short.jwt_signing_keys == "kid:short"

    _production_env(monkeypatch)
    monkeypatch.setenv("ALGORITHM", "HS256")
    with pytest.raises(ValueError, match="HS256 is prohibited"):
        SecuritySettings()

    with pytest.raises(ValueError, match="JWT_AUDIENCE must not be empty"):
        SecuritySettings(jwt_audience="")


def test_jwt_signing_registry_parses_entries_caches_and_exposes_aliases():
    settings = _mixin(
        jwt_signing_keys=[" first : first-secret ", "second:second-secret"],
        jwt_active_kid=" first ",
        algorithm="RS256",
        jwt_private_key_path="",
        secret_key="fallback",
        environment="development",
    )

    registry = settings.jwt_signing_key_registry
    assert registry == {"first": "first-secret", "second": "second-secret"}
    assert settings.jwt_signing_key_registry is registry
    assert settings.jwt_signing_active_kid == "first"
    assert settings.jwt_signing_active_secret == "first-secret"
    assert settings.SECRET_KEY == "first-secret"
    assert settings.ALGORITHM == "RS256"


@pytest.mark.parametrize(
    "entries, message",
    [
        ("missing-separator", "format"),
        (":secret", "non-empty kid"),
        ("kid:", "non-empty secret"),
        (["kid:secret", "kid:other"], "unique kid"),
    ],
)
def test_jwt_signing_registry_rejects_malformed_entries(entries, message):
    settings = _mixin(
        jwt_signing_keys=entries,
        jwt_active_kid=None,
        algorithm="HS256",
        jwt_private_key_path="",
        secret_key="fallback",
        environment="development",
    )

    with pytest.raises(RuntimeError, match=message):
        _ = settings.jwt_signing_key_registry


def test_jwt_registry_falls_back_to_secret_and_validates_active_kid():
    fallback = _mixin(
        jwt_signing_keys="",
        jwt_active_kid="",
        algorithm="HS256",
        jwt_private_key_path="",
        secret_key="fallback",
        environment="development",
    )
    assert fallback.jwt_signing_key_registry == {"primary": "fallback"}
    assert fallback.jwt_signing_active_kid == "primary"

    invalid = _mixin(
        jwt_signing_keys="kid:secret",
        jwt_active_kid="other",
        algorithm="HS256",
        jwt_private_key_path="",
        secret_key="fallback",
        environment="development",
    )
    with pytest.raises(RuntimeError, match="must match"):
        _ = invalid.jwt_signing_active_kid


def test_jwt_active_secret_fails_closed_when_active_key_is_absent():
    class _BrokenRegistry(JwtSettingsMixin):
        @property
        def jwt_signing_key_registry(self) -> dict[str, str]:
            return {}

        @property
        def jwt_signing_active_kid(self) -> str:
            return "primary"

    settings = _BrokenRegistry()
    with pytest.raises(RuntimeError, match="does not contain the active kid"):
        _ = settings.jwt_signing_active_secret
