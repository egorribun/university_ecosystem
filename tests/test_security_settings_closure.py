"""Closure tests for comma-only audit secrets and default campus subnets."""

import pytest

from app.core.config.security import SecuritySettings


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


def test_audit_log_secret_warns_for_placeholder_in_development(caplog):
    caplog.set_level("WARNING")

    SecuritySettings(
        environment="development",
        audit_log_secret="placeholder-" + "a" * 32,
    )

    assert "AUDIT_LOG_SECRET looks like a placeholder" in caplog.text


def test_audit_log_secret_rejects_placeholder_and_short_values_in_production(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="contains a placeholder"):
        SecuritySettings(audit_log_secret="placeholder-" + "a" * 32)

    with pytest.raises(ValueError, match="at least 32 characters"):
        SecuritySettings(audit_log_secret="a" * 31)


def test_internal_hmac_secret_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="INTERNAL_HMAC_SECRET MUST be set"):
        SecuritySettings(
            audit_log_secret="a" * 32,
            internal_hmac_secret="",
        )
