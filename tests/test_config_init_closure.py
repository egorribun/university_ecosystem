"""Branch closure tests for composed Settings behavior."""

from app.core.config import Settings


def test_dependent_settings_skips_cache_warning_for_non_redis_backend():
    settings = Settings(_allow_missing=True)
    settings.environment = "production"
    settings.cache_backend = "memory"
    settings.database_pool_size = 5
    settings.database_max_overflow = 10
    settings.database_read_replica_url = ""

    assert settings._validate_dependent_settings() is settings


def test_dependent_settings_accepts_custom_redis_url_without_warning_path():
    settings = Settings(_allow_missing=True)
    settings.environment = "production"
    settings.cache_backend = "redis"
    settings.cache_redis_url = "redis://cache.internal:6379/0"
    settings.database_pool_size = 5
    settings.database_max_overflow = 10
    settings.database_read_replica_url = ""

    assert settings._validate_dependent_settings() is settings


def test_app_base_url_clean_prefers_configured_base_url():
    settings = Settings(_allow_missing=True)
    settings.app_base_url = "https://api.example.com/"
    settings.frontend_origin = "https://frontend.example.com/"

    assert settings.app_base_url_clean == "https://api.example.com"
