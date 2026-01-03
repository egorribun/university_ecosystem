import importlib
from contextlib import contextmanager
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT



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


def test_settings_warn_when_env_matches_example(monkeypatch, caplog, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    # Create a complete .env.example with all required vars for the test
    secret_key = "Qj7p4R2zYx8N1a5Hk9V3u0Mw6Tg4Lr8Cz2Jv5Qw7Xn1Dk6Fh0Sg3Vb9Pp4Rz8Lm2"
    test_example_content = (
        f"DATABASE_URL=postgresql+asyncpg://test:test@localhost/test\nSECRET_KEY={secret_key}\n"
    ).encode()

    # Write both .env and .env.example with identical content
    example_path = BACKEND_ROOT / ".env.example"
    original_example = None
    try:
        original_example = example_path.read_bytes()
    except FileNotFoundError:
        pass

    try:
        example_path.write_bytes(test_example_content)

        with _temporary_env_file(test_example_content) as env_path:
            from app.core import config as config_module

            with caplog.at_level("WARNING"):
                config_module = importlib.reload(config_module)

            assert env_path.resolve() == config_module._ENV_FILE

            with caplog.at_level("WARNING"):
                settings = config_module.Settings()

        assert settings.database_url.startswith("postgresql+")
        assert settings.secret_key == secret_key
        assert any("identical to" in record.getMessage() for record in caplog.records)
    finally:
        # Restore original .env.example
        if original_example is not None:
            example_path.write_bytes(original_example)
        elif example_path.exists():
            example_path.unlink()


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


def test_auto_create_schema_default_true_in_development(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("SECRET_KEY", "development-secret")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        settings = config_module.Settings()

    assert settings.auto_create_schema is True


def test_auto_create_schema_default_false_in_production(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("SECRET_KEY", "production-secret")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        settings = config_module.Settings()

    assert settings.auto_create_schema is False


def test_auto_create_schema_warns_when_enabled_in_production(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("SECRET_KEY", "production-secret")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")

    with _temporary_env_file(None):
        from app.core import config as config_module

        with caplog.at_level("WARNING"):
            config_module = importlib.reload(config_module)
            settings = config_module.Settings()

    assert settings.auto_create_schema is True
    assert any(
        "AUTO_CREATE_SCHEMA is enabled" in record.getMessage()
        for record in caplog.records
    )


def test_response_compression_toggle(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("SECRET_KEY", "testing-secret")
    monkeypatch.delenv("ENABLE_RESPONSE_COMPRESSION", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        default_settings = config_module.Settings()
        assert default_settings.response_compression_enabled is True
        assert (
            config_module.settings.response_compression_enabled
            == default_settings.response_compression_enabled
        )

        monkeypatch.setenv("ENABLE_RESPONSE_COMPRESSION", "false")
        config_module = importlib.reload(config_module)
        disabled_settings = config_module.Settings()
        assert disabled_settings.response_compression_enabled is False
        assert (
            config_module.settings.response_compression_enabled
            == disabled_settings.response_compression_enabled
        )
