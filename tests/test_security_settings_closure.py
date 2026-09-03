"""Closure tests for comma-only audit secrets and default campus subnets."""

from unittest.mock import patch

import pytest

from app.core.config.security import SecuritySettings

_RETIRED_AUDIT_KEYS = (
    "".join(("f3d9a1c2", "e4b5a6d7", "c8e9f0a1", "b2c3d4e5")),
    "".join(("86dfd546", "41624c4e", "8ae58a2d", "18449c25")),
)


def test_audit_log_secret_rejects_comma_only_value():
    with pytest.raises(ValueError, match="AUDIT_LOG_SECRET must not be empty"):
        SecuritySettings(audit_log_secret=",,,")


def test_campus_subnets_none_uses_safe_defaults():
    settings = SecuritySettings(campus_subnets=None)

    assert settings.campus_subnets == [
        "192.168.0.0/16",
        "10.0.0.0/8",
        "127.0.0.1/32",
    ]


def test_audit_log_secret_warns_for_placeholder_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")

    with patch("app.core.config.security._logger") as logger:
        SecuritySettings(  # pragma: allowlist secret
            algorithm="RS256",
            audit_log_secret="placeholder-" + "a" * 32,  # pragma: allowlist secret
        )

    assert (
        "AUDIT_LOG_SECRET looks like a placeholder" in logger.warning.call_args.args[0]
    )


def test_audit_log_secret_rejects_placeholder_and_short_values_in_production(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="contains a placeholder"):
        SecuritySettings(  # pragma: allowlist secret
            audit_log_secret="placeholder-" + "a" * 32  # pragma: allowlist secret
        )

    with pytest.raises(ValueError, match="at least 32 characters"):
        SecuritySettings(audit_log_secret="a" * 31)


def test_internal_hmac_secret_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="INTERNAL_HMAC_SECRET MUST be set"):
        SecuritySettings(
            audit_log_secret="a" * 32,
            internal_hmac_secret="",
        )


def test_default_audit_secret_is_rejected_in_production(monkeypatch):
    """A settings instance must not retain the repository-known sentinel."""
    from app.core.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "testing")
    configured = Settings(_allow_missing=True)
    configured.environment = "production"
    configured.audit_log_secret = "_".join(
        ("CHANGE", "ME", "GENERATE", "64", "BYTE", "AUDIT", "LOG", "SECRET")
    )

    with pytest.raises(ValueError, match="AUDIT_LOG_SECRET must be explicitly"):
        configured._reject_default_audit_secret_in_production()


@pytest.mark.parametrize("retired_key", _RETIRED_AUDIT_KEYS)
def test_retired_repository_audit_keys_are_rejected_in_production(
    monkeypatch, retired_key
):
    """Previously shipped signing keys must remain blocked after rotation."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="placeholder"):
        SecuritySettings(
            audit_log_secret=retired_key,
            internal_hmac_secret="h" * 32,
        )

    with pytest.raises(ValueError, match="placeholder"):
        SecuritySettings(
            audit_log_secret=retired_key.upper(),
            internal_hmac_secret="h" * 32,
        )


@pytest.mark.parametrize("value", ["not-hex", "ab" * 31, "abc", "ab " * 32])
def test_imgproxy_secrets_reject_invalid_or_short_hex(value):
    with pytest.raises(ValueError, match="IMGPROXY_KEY must be at least 32 bytes"):
        SecuritySettings(imgproxy_key=value)


def test_imgproxy_secrets_accept_32_byte_hex_values():
    settings = SecuritySettings(
        imgproxy_key="ab" * 32,
        imgproxy_salt="cd" * 32,
    )

    assert settings.imgproxy_key == "ab" * 32
    assert settings.imgproxy_salt == "cd" * 32
