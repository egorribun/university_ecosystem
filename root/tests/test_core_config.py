import pytest


def test_settings_require_real_secret_when_env_missing(monkeypatch):
    """When no .env is provided the app should not fall back to sample secrets."""

    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app.core import config as config_module

    assert config_module._ENV_FILE is None

    with pytest.raises(RuntimeError) as exc_info:
        config_module.Settings()

    combined = str(exc_info.value).lower()

    assert "missing required environment settings" in combined
    assert "secret_key" in combined
    assert "provide real secrets" in combined
    assert "validationerror" not in combined
