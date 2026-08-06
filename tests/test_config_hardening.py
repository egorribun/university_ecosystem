import pytest

from app.core.config.base import BaseAppSettings, _should_allow_development_defaults


def test_config_hardening_policy(monkeypatch):
    """
    Verify that _should_allow_development_defaults strictly requires
    explicit development environment.
    """
    # 1. Unset/Production -> False
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _should_allow_development_defaults() is False

    monkeypatch.setenv("ENVIRONMENT", "production")
    assert _should_allow_development_defaults() is False

    # 2. Dev/Test -> True (if no env vars/files block it)
    monkeypatch.setenv("ENVIRONMENT", "dev")
    import importlib

    config_base = importlib.import_module("app.core.config.base")

    monkeypatch.setattr(config_base, "_ENV_FILE", None)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _should_allow_development_defaults() is True


def test_config_hardening_enforcement(monkeypatch):
    """
    Verify that BaseAppSettings raises RuntimeError in production
    when fields are missing.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")

    from pydantic_settings import SettingsConfigDict

    class HardenedSettings(BaseAppSettings):
        # Use a unique field name to avoid pollution from global test env
        required_field_missing: str
        model_config = SettingsConfigDict(env_file=None)

    with pytest.raises(RuntimeError) as excinfo:
        HardenedSettings(_allow_missing=True)

    assert "Missing required environment variables" in str(excinfo.value)
    assert "REQUIRED_FIELD_MISSING" in str(excinfo.value)


def test_config_fallback_generation(monkeypatch):
    """
    Verify that BaseAppSettings DOES generate fallbacks in dev.
    """
    monkeypatch.setenv("ENVIRONMENT", "local")
    import importlib

    config_base = importlib.import_module("app.core.config.base")

    monkeypatch.setattr(config_base, "_ENV_FILE", None)

    from pydantic_settings import SettingsConfigDict

    class FallbackSettings(BaseAppSettings):
        secret_key: str
        model_config = SettingsConfigDict(env_file=None)

    # In conftest, SECRET_KEY might be present.
    # But if we use _allow_missing=True, it will try to generate if missing.
    # To test GENERATION, we must be missing it.
    monkeypatch.delenv("SECRET_KEY", raising=False)

    # We use a unique field name that HAS a fallback in base.py
    # e.g. database_url
    class FallbackDbSettings(BaseAppSettings):
        database_url: str
        model_config = SettingsConfigDict(env_file=None)

    monkeypatch.delenv("DATABASE_URL", raising=False)

    s = FallbackDbSettings(_allow_missing=True)
    assert s.database_url == "sqlite+aiosqlite:///./dev.db"
