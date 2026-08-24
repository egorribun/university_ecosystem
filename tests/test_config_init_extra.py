import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.config.__init__ import (
    DatabaseSettings,
    SecuritySettings,
    _load_settings,
    _NamespaceView,
)


def test_namespace_view():
    """Test the _NamespaceView delegation helper."""
    parent = MagicMock()
    parent.test_attr = "val"

    view = _NamespaceView(parent, DatabaseSettings)
    assert view.test_attr == "val"
    assert repr(view) == "<_NamespaceView(DatabaseSettings)>"


def test_config_reject_insecure_production():
    """Test insecure production configuration validation checks."""
    settings = Settings(_allow_missing=True)

    # 1. Non-production or SQLite database doesn't raise
    settings.environment = "development"
    settings.minio_secure = False
    assert settings._reject_insecure_production_config() is settings

    settings.environment = "production"
    settings.database_url = "sqlite+aiosqlite:///test.db"
    assert settings._reject_insecure_production_config() is settings

    # 2. Production PostgreSQL raises on MinIO insecure
    settings.database_url = "postgresql+asyncpg://localhost/db"
    settings.minio_secure = False
    with pytest.raises(
        ValueError, match="MINIO_SECURE must be true in production/staging"
    ):
        settings._reject_insecure_production_config()

    # 3. Production PostgreSQL raises on HTTP Elasticsearch
    settings.minio_secure = True
    settings.elasticsearch_url = "http://localhost:9200"
    with pytest.raises(ValueError, match="ELASTICSEARCH_URL must use https://"):
        settings._reject_insecure_production_config()

    settings.elasticsearch_url = "https://localhost:9200"
    assert settings._reject_insecure_production_config() is settings


def test_config_security_invariants():
    """Test Spotify and NATS security validation in production."""
    settings = Settings(_allow_missing=True)
    settings.environment = "production"

    # Missing spotify token
    settings.spotify_token_secret = ""
    with pytest.raises(ValueError, match="SPOTIFY_TOKEN_SECRET required in production"):
        settings._validate_security_invariants()

    # Missing NATS auth token
    settings.spotify_token_secret = "secret"  # pragma: allowlist secret
    settings.nats_auth_token = ""
    with pytest.raises(ValueError, match="NATS_AUTH_TOKEN required in production"):
        settings._validate_security_invariants()


def test_config_security_invariants_accept_complete_production_credentials():
    settings = Settings(_allow_missing=True)
    settings.environment = "production"
    settings.spotify_token_secret = "spotify-test-secret"  # pragma: allowlist secret
    settings.nats_auth_token = "nats-test-secret"  # pragma: allowlist secret

    assert settings._validate_security_invariants() is settings


def test_auto_create_schema_false_skips_production_warning():
    with patch("app.core.config._logger") as mock_logger:
        Settings(_allow_missing=True, auto_create_schema=False)

    assert not any(
        "AUTO_CREATE_SCHEMA is enabled" in str(call.args[0])
        for call in mock_logger.warning.call_args_list
    )


def test_config_dependent_settings_warnings():
    """Test low pool size and identical read replica warnings in production."""
    settings = Settings(_allow_missing=True)
    settings.environment = "production"

    # Low pool size warning
    settings.database_pool_size = 1
    settings.database_max_overflow = 1
    with patch("app.core.config._logger") as mock_logger:
        settings._validate_dependent_settings()
    assert any(
        "database_pool_size" in str(call.args[0])
        for call in mock_logger.warning.call_args_list
    )

    # Identical read replica warning
    settings.database_pool_size = 10
    settings.database_max_overflow = 10
    settings.database_url = "postgresql://primary"
    settings.database_read_replica_url = "postgresql://primary"
    with patch("app.core.config._logger") as mock_logger:
        settings._validate_dependent_settings()
    assert any(
        "database_read_replica_url is identical to database_url" in str(call.args[0])
        for call in mock_logger.warning.call_args_list
    )


def test_app_base_url_clean():
    """Test cleaning app_base_url and falling back to origins."""
    settings = Settings(_allow_missing=True)

    # Defaults
    settings.app_base_url = None
    settings.frontend_origin = None
    settings.frontend_origins_list = []
    assert settings.app_base_url_clean == "http://localhost:5173"

    # Use a new Settings object to bypass cached_property
    settings_new = Settings(_allow_missing=True)
    settings_new.app_base_url = None
    settings_new.frontend_origin = None
    settings_new.frontend_origins_list = ["https://origin1/", "https://origin2/"]
    assert settings_new.app_base_url_clean == "https://origin1"


def test_namespace_properties():
    """Verify that cached namespace properties correctly instantiate views."""
    settings = Settings(_allow_missing=True)

    assert type(settings.db).__name__ == "_NamespaceView"
    assert settings.db.database_pool_size == settings.database_pool_size

    assert type(settings.security).__name__ == "_NamespaceView"
    assert type(settings.cache).__name__ == "_NamespaceView"
    assert type(settings.observability).__name__ == "_NamespaceView"
    assert type(settings.storage).__name__ == "_NamespaceView"
    assert type(settings.notifications).__name__ == "_NamespaceView"
    assert type(settings.integrations).__name__ == "_NamespaceView"
    assert type(settings.app).__name__ == "_NamespaceView"


def test_load_settings_fallbacks():
    """Test fallback loading logic in _load_settings when constructor raises error."""
    exc = RuntimeError("Simulated missing required")
    exc.missing_required = ["database_url"]

    # 1. If _base_should_allow returns False -> re-raises
    with (
        patch("app.core.config.__init__.Settings", side_effect=exc),
        patch("app.core.config.__init__._base_should_allow", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="Simulated missing required"):
            _load_settings()

    # 2. Fallback allowed: CI=true
    ci_fallback = MagicMock()
    ci_fallback.development_fallback_fields = ("database_url",)
    with (
        patch("app.core.config.__init__.Settings") as mock_settings_class,
        patch("app.core.config.__init__._base_should_allow", return_value=True),
        patch("app.core.config.__init__._logger") as mock_logger,
        patch("app.core.config.__init__._PROJECT_ROOT") as mock_root,
        patch.dict(os.environ, {"CI": "true"}),
    ):
        # Make the first call raise exc, second call (fallback) return a dummy
        mock_settings_class.side_effect = [exc, ci_fallback]
        # mock .env to not exist
        mock_root.__truediv__.return_value.exists.return_value = False

        _load_settings()
        mock_logger.warning.assert_called()

    # 4. Missing fallback metadata and an existing .env use the safe defaults
    # without adding a filesystem hint.
    fallback = MagicMock()
    fallback.development_fallback_fields = ()
    with (
        patch("app.core.config.__init__.Settings") as mock_settings_class,
        patch("app.core.config.__init__._base_should_allow", return_value=True),
        patch("app.core.config.__init__._logger") as mock_logger,
        patch("app.core.config.__init__._PROJECT_ROOT") as mock_root,
        patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}),
    ):
        mock_settings_class.side_effect = [exc, fallback]
        mock_root.__truediv__.return_value.exists.return_value = True

        result = _load_settings()

    assert result is fallback
    assert mock_logger.warning.call_args.args[1] == "DATABASE_URL, SECRET_KEY"

    # 3. Fallback allowed: Local dev (no CI)
    with (
        patch("app.core.config.__init__.Settings") as mock_settings_class,
        patch("app.core.config.__init__._base_should_allow", return_value=True),
        patch("app.core.config.__init__._logger") as mock_logger,
        patch("app.core.config.__init__._PROJECT_ROOT") as mock_root,
        patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}),
    ):
        mock_settings_class.side_effect = [exc, ci_fallback]
        mock_root.__truediv__.return_value.exists.return_value = False

        _load_settings()
        mock_logger.warning.assert_called()


def test_force_reload_security_config() -> None:
    """Force re-importing app.core.config.security under coverage to execute class-level declarations."""
    import importlib

    import app.core as app_core

    modules_to_delete = [
        "app.core.config.security",
        "app.core.config",
    ]
    original_modules = {mod: sys.modules.get(mod) for mod in modules_to_delete}
    missing = object()
    original_config_attr = getattr(app_core, "config", missing)
    try:
        for mod in modules_to_delete:
            sys.modules.pop(mod, None)

        import app.core.config.security as sec

        importlib.reload(sec)
    finally:
        for mod, original_module in original_modules.items():
            if original_module is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = original_module
        if original_config_attr is missing:
            delattr(app_core, "config")
        else:
            app_core.config = original_config_attr


def test_audit_log_secret_validation():
    """Verify validation and warnings/exceptions for AUDIT_LOG_SECRET in various envs."""
    # 1. Empty secret
    with pytest.raises(ValueError, match="AUDIT_LOG_SECRET must not be empty"):
        SecuritySettings(audit_log_secret="")

    # 2. Placeholder warning in development
    # Construct key that is >= 32 chars but contains a placeholder
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "development"}),
        patch("app.core.config.security._logger") as mock_logger,
    ):
        _ = SecuritySettings(
            environment="development",
            algorithm="RS256",
            audit_log_secret="change-me-long-secret-key-32-chars-long",  # pragma: allowlist secret
        )
    assert any(
        "looks like a placeholder" in str(call.args[0])
        for call in mock_logger.warning.call_args_list
    )

    # 3. Placeholder error in production
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with pytest.raises(ValueError, match="AUDIT_LOG_SECRET contains a placeholder"):
            SecuritySettings(
                environment="production",
                audit_log_secret="change-me-long-secret-key-32-chars-long",  # pragma: allowlist secret
            )

    # 4. Too short secret
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with pytest.raises(
            ValueError, match="entries must be at least 32 characters long"
        ):
            SecuritySettings(
                environment="production",
                audit_log_secret="too-short",  # pragma: allowlist secret
            )


def test_integration_settings_file_secrets():
    """Verify Docker/K8s Secrets loading for IntegrationSettings."""
    from app.core.config.integrations import IntegrationSettings

    with patch("app.core.config.integrations._load_file_secret") as mock_load:
        loaded = "loaded-from-file"  # pragma: allowlist secret
        mock_load.side_effect = lambda env_name, v: (
            loaded
            if env_name
            in [
                "SPOTIFY_CLIENT_SECRET_FILE",
                "SPICEDB_PRESHARED_KEY_FILE",
                "ELASTICSEARCH_PASSWORD_FILE",
                "WS_HUB_INTERNAL_SECRET_FILE",
            ]
            else v
        )

        s = IntegrationSettings(
            _allow_missing=True,
            environment="development",
            spotify_client_secret="dummy",  # pragma: allowlist secret
            spicedb_preshared_key="dummy",  # pragma: allowlist secret
            elasticsearch_password="dummy",  # pragma: allowlist secret
            ws_hub_internal_secret="dummy",  # pragma: allowlist secret
        )
        assert s.spotify_client_secret == loaded
        assert s.spicedb_preshared_key == loaded
        assert s.elasticsearch_password == loaded
        assert s.ws_hub_internal_secret == loaded


def test_integration_settings_production_validation():
    """Verify production-only secret validation rules in IntegrationSettings."""
    from app.core.config.integrations import IntegrationSettings

    prod_env = {"ENVIRONMENT": "production", "CI": "false", "GITHUB_ACTIONS": "false"}

    # 1. Missing elasticsearch password
    with patch.dict(os.environ, prod_env):
        with pytest.raises(ValueError, match="ELASTICSEARCH_PASSWORD is required"):
            IntegrationSettings(_allow_missing=True, elasticsearch_password="")

    # 2. SpiceDB preshared key using default development value
    with patch.dict(os.environ, prod_env):
        with pytest.raises(
            ValueError, match="SPICEDB_PRESHARED_KEY must not use the default"
        ):
            IntegrationSettings(
                _allow_missing=True,
                elasticsearch_password="secure-password",  # pragma: allowlist secret
                spicedb_preshared_key="development-preshared-key",
            )

    # 3. Spotify enabled but OAuth state secret missing
    with patch.dict(os.environ, prod_env):
        with pytest.raises(ValueError, match="SPOTIFY_OAUTH_STATE_SECRET must be set"):
            IntegrationSettings(
                _allow_missing=True,
                elasticsearch_password="secure-password",  # pragma: allowlist secret
                spicedb_preshared_key="secure-preshared-key",
                spotify_client_id="some-client-id",
                spotify_oauth_state_secret="",
            )

    # 4. WS hub internal secret missing
    with patch.dict(os.environ, prod_env):
        with pytest.raises(ValueError, match="WS_HUB_INTERNAL_SECRET must be set"):
            IntegrationSettings(
                _allow_missing=True,
                elasticsearch_password="secure-password",  # pragma: allowlist secret
                spicedb_preshared_key="secure-preshared-key",
                spotify_client_id="some-client-id",
                spotify_oauth_state_secret="secure-state-secret",  # pragma: allowlist secret
                ws_hub_internal_secret="",
            )

    # 5. Success in production with secure values
    with patch.dict(os.environ, prod_env):
        s = IntegrationSettings(
            _allow_missing=True,
            elasticsearch_password="secure-password",  # pragma: allowlist secret
            spicedb_preshared_key="secure-preshared-key",
            spotify_client_id="some-client-id",
            spotify_oauth_state_secret="secure-state-secret",  # pragma: allowlist secret
            ws_hub_internal_secret="secure-internal-secret",  # pragma: allowlist secret
        )
        assert s.elasticsearch_password == "secure-password"  # pragma: allowlist secret
