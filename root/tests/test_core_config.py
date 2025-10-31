import importlib
from contextlib import contextmanager
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "root"


@contextmanager
def _temporary_env_file(content: bytes | None):
    env_path = BACKEND_ROOT / ".env"
    try:
        original = env_path.read_bytes()
    except FileNotFoundError:
        original = None

    try:
        if content is None:
            if env_path.exists():
                env_path.unlink()
        else:
            env_path.write_bytes(content)
        yield env_path
    finally:
        if original is None:
            if env_path.exists():
                env_path.unlink()
        else:
            env_path.write_bytes(original)


def test_settings_require_real_secret_when_env_missing(monkeypatch):
    """When no .env is provided the app should not fall back to sample secrets."""

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)

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


def test_settings_allow_development_defaults_when_opted_in(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)

        settings = config_module.Settings(_allow_missing=True)

        assert settings.database_url == "sqlite+aiosqlite:///./dev.db"
        assert settings.secret_key == "development-secret-key"
        assert settings.has_development_fallbacks is True
        assert set(settings.development_fallback_fields) == {
            "database_url",
            "secret_key",
        }

        assert config_module.settings.has_development_fallbacks is True


def test_settings_warn_when_env_matches_example(monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    example_bytes = (BACKEND_ROOT / ".env.example").read_bytes()

    with _temporary_env_file(example_bytes) as env_path:
        from app.core import config as config_module

        with caplog.at_level("WARNING"):
            config_module = importlib.reload(config_module)

        assert config_module._ENV_FILE == env_path.resolve()

        with caplog.at_level("WARNING"):
            settings = config_module.Settings()

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert (
        settings.secret_key
        == "Qj7p4R2zYx8N1a5Hk9V3u0Mw6Tg4Lr8Cz2Jv5Qw7Xn1Dk6Fh0Sg3Vb9Pp4Rz8Lm2"
    )
    assert any("identical to" in record.getMessage() for record in caplog.records)


def test_notifications_allowed_push_topics_parsed(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv(
        "NOTIFICATIONS_ALLOWED_PUSH_TOPICS",
        "alerts, Schedule,alerts , System ",
    )

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        settings = config_module.Settings(_allow_missing=True)

    assert settings.notifications_allowed_push_topics == [
        "alerts",
        "schedule",
        "system",
    ]
    assert settings.notifications_allowed_push_topics_set == {
        "alerts",
        "schedule",
        "system",
    }
