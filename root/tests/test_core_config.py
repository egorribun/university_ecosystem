import pytest
from pydantic import ValidationError


def test_settings_require_real_secret_when_env_missing(monkeypatch):
    """When no .env is provided the app should not fall back to sample secrets."""

    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app.core import config as config_module

    assert config_module._ENV_FILE is None

    with pytest.raises(ValidationError) as exc_info:
        config_module.Settings()

    parts = [str(exc_info.value)]
    parts.extend(getattr(exc_info.value, "__notes__", []) or [])
    combined = " ".join(part.lower() for part in parts)

    assert "missing required environment settings" in combined
    assert "secret_key" in combined
    assert "provide real secrets" in combined
