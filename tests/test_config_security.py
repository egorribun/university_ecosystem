import pytest
from pydantic import ValidationError

from app.core.config.security import SecuritySettings


class TestSecuritySettings:
    def test_secret_key_min_length_production(self, monkeypatch):
        # Mock production environment
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "short")

        with pytest.raises(ValidationError) as exc:
            SecuritySettings(secret_key="short")

        assert "SECRET_KEY must be at least 32 characters" in str(exc.value)

    def test_secret_key_min_length_development(self, monkeypatch):
        # Mock development environment
        monkeypatch.setenv("ENVIRONMENT", "development")
        # Should NOT raise error
        settings = SecuritySettings(secret_key="short", algorithm="RS256")
        assert settings.secret_key == "short"

    def test_jwt_signing_keys_entropy(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv(
            "SECRET_KEY", "long_enough_secret_key_for_production_use_case"
        )

        # Weak key in rotate list
        with pytest.raises(ValidationError) as exc:
            SecuritySettings(
                secret_key="long_enough_secret_key_for_production_use_case",
                jwt_signing_keys="kid1:short",
            )
        assert "JWT_SIGNING_KEYS entries must be at least 32 characters" in str(
            exc.value
        )

    def test_campus_subnets_defaults(self):
        settings = SecuritySettings()
        assert settings.campus_subnets == [
            "192.168.0.0/16",
            "10.0.0.0/8",
            "127.0.0.1/32",
        ]

    def test_campus_subnets_custom_string(self, monkeypatch):
        monkeypatch.setenv("CAMPUS_SUBNETS", "10.5.0.0/16, 172.16.0.0/12")
        settings = SecuritySettings()
        assert settings.campus_subnets == ["10.5.0.0/16", "172.16.0.0/12"]

    def test_control_work_grace_minutes_default_and_custom(self, monkeypatch):
        settings_default = SecuritySettings()
        assert settings_default.control_work_grace_minutes == 15

        monkeypatch.setenv("CONTROL_WORK_GRACE_MINUTES", "30")
        settings_custom = SecuritySettings()
        assert settings_custom.control_work_grace_minutes == 30
