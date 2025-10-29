import pytest


def test_settings_require_real_secret_when_env_missing(monkeypatch):
    """When no .env is provided the app should not fall back to sample secrets."""

    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app.core import config as config_module

    assert config_module._ENV_FILE is None

    with pytest.raises(RuntimeError) as exc_info:
        config_module.Settings()

    message = str(exc_info.value)
    combined = message.lower()

    assert "missing required environment variables" in combined
    assert "secret_key" not in message
    assert "SECRET_KEY" in message
    assert "provide real secrets" in combined
    assert "validationerror" not in combined
