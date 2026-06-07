import importlib
import os
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT


@pytest.fixture(autouse=True)
def restore_config_module():
    """Restores the config module to its original state after each test."""
    from app.core import config as config_module
    from app.core.config import base as base_module

    original_env = dict(os.environ)
    # importlib.reload(config_module) rebinds config_module.settings to a NEW
    # Settings() instance (config/__init__.py:310 `settings = _load_settings()`),
    # which permanently diverges from the ORIGINAL singleton that ~90 modules
    # captured via `from app.core.config import settings` at their own import time
    # (e.g. command_service). A later test that does monkeypatch.setattr(settings, …)
    # then patches the reloaded object while those modules keep reading the original
    # -> a silent cross-module isolation break (e.g. chat_attachment_max_files=0 never
    # reaches command_service -> the upload is saved -> ck_attachment_url_scheme).
    # Capture the original instance and reinstate it after the cleanup reload so
    # singleton identity (and cross-module monkeypatch) survives the reloads. This is a
    # latent seed-dependent flake in randomized CI; mutmut (2x pytest.main() in one
    # process: stats run -> clean-test) makes it deterministic.
    original_settings = config_module.settings
    yield
    os.environ.clear()
    os.environ.update(original_env)

    importlib.reload(base_module)
    importlib.reload(config_module)
    config_module.settings = original_settings


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
        from app.core.config import base as base_module

        importlib.reload(base_module)
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
        from app.core.config import base as base_module

        importlib.reload(base_module)
        config_module = importlib.reload(config_module)

        settings = config_module.Settings(_allow_missing=True)

        assert settings.database_url == "sqlite+aiosqlite:///./dev.db"
        assert isinstance(settings.secret_key, str)
        assert len(settings.secret_key) > 0
        assert settings.has_development_fallbacks is True
        assert set(settings.development_fallback_fields) == {
            "database_url",
            "secret_key",
        }

        assert config_module.settings.has_development_fallbacks is True


def test_settings_warn_when_env_matches_example(monkeypatch, caplog, tmp_path):
    # Create a complete .env.example with all required vars for the test
    secret_key = "Qj7p4R2zYx8N1a5Hk9V3u0Mw6Tg4Lr8Cz2Jv5Qw7Xn1Dk6Fh0Sg3Vb9Pp4Rz8Lm2"
    database_url = "postgresql+asyncpg://test:test@localhost/test"
    test_example_content = (
        f"DATABASE_URL={database_url}\nSECRET_KEY={secret_key}\n"
    ).encode()

    # Set env vars directly to work around Pydantic caching model_config.env_file
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_KEY", secret_key)

    # Write both .env and .env.example with identical content
    example_path = BACKEND_ROOT / ".env.example"
    original_example = None
    with suppress(FileNotFoundError):
        original_example = example_path.read_bytes()

    try:
        example_path.write_bytes(test_example_content)

        with _temporary_env_file(test_example_content) as env_path:
            from app.core import config as config_module
            from app.core.config import base as base_module

            with caplog.at_level("WARNING"):
                importlib.reload(base_module)
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
        from app.core.config import base as base_module

        importlib.reload(base_module)
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
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    db_name = f"test_{worker_id}.db" if worker_id else "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///./{db_name}")
    monkeypatch.setenv("SECRET_KEY", "development-secret")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        settings = config_module.Settings()

    assert settings.auto_create_schema is True


def test_auto_create_schema_default_false_in_production(monkeypatch, tmp_path):
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    db_name = f"test_{worker_id}.db" if worker_id else "test.db"

    # Create fake public key for production invariants validation
    mock_key = tmp_path / "jwt.pem"
    mock_key.write_text("-----BEGIN PUBLIC KEY-----\nmock\n-----END PUBLIC KEY-----")

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///./{db_name}")
    monkeypatch.setenv("SECRET_KEY", "production-secret-must-be-at-least-32-chars-long")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(mock_key))
    monkeypatch.setenv("INTERNAL_AUTH_TOKEN", "dummy_token_for_test")
    monkeypatch.setenv("AUDIT_LOG_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("NATS_AUTH_TOKEN", "dummy_nats_token")
    monkeypatch.setenv("SPOTIFY_TOKEN_SECRET", "dummy_spotify_secret")
    monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "dummy_elastic_pass")
    monkeypatch.setenv("SPICEDB_PRESHARED_KEY", "prod-preshared-key-for-test")
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "a" * 32)
    monkeypatch.setenv("WS_HUB_INTERNAL_SECRET", "dummy_ws_hub_secret_for_test")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    with _temporary_env_file(None):
        from app.core import config as config_module

        config_module = importlib.reload(config_module)
        settings = config_module.Settings()

    assert settings.auto_create_schema is False


def test_auto_create_schema_warns_when_enabled_in_production(
    monkeypatch, caplog, tmp_path
):
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    db_name = f"test_{worker_id}.db" if worker_id else "test.db"

    # Create fake public key for production invariants validation
    mock_key = tmp_path / "jwt.pem"
    mock_key.write_text("-----BEGIN PUBLIC KEY-----\nmock\n-----END PUBLIC KEY-----")

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///./{db_name}")
    monkeypatch.setenv("SECRET_KEY", "production-secret-must-be-at-least-32-chars-long")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(mock_key))
    monkeypatch.setenv("INTERNAL_AUTH_TOKEN", "dummy_token_for_test")
    monkeypatch.setenv("AUDIT_LOG_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("NATS_AUTH_TOKEN", "dummy_nats_token")
    monkeypatch.setenv("SPOTIFY_TOKEN_SECRET", "dummy_spotify_secret")
    monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "dummy_elastic_pass")
    monkeypatch.setenv("SPICEDB_PRESHARED_KEY", "prod-preshared-key-for-test")
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "a" * 32)
    monkeypatch.setenv("WS_HUB_INTERNAL_SECRET", "dummy_ws_hub_secret_for_test")
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
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    db_name = f"test_{worker_id}.db" if worker_id else "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///./{db_name}")
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
