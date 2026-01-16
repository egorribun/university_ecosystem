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
        settings = SecuritySettings(secret_key="short")
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
