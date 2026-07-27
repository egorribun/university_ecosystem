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
