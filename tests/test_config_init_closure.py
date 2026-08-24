"""Branch closure tests for composed Settings behavior."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.config.__init__ import DatabaseSettings, SecuritySettings, _NamespaceView


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


def test_dependent_settings_requires_revocation_url_outside_development():
    settings = Settings(_allow_missing=True)
    settings.environment = "production"
    settings.revocation_redis_url = ""

    with pytest.raises(ValueError, match="REVOCATION_REDIS_URL is required"):
        settings._validate_dependent_settings()


def test_dependent_settings_requires_distinct_revocation_process():
    settings = Settings(_allow_missing=True)
    settings.environment = "production"
    settings.cache_redis_url = "redis://cache.internal:6379/0"
    settings.revocation_redis_url = "redis://cache.internal:6379/9"

    with pytest.raises(ValueError, match="must use a distinct Redis process"):
        settings._validate_dependent_settings()


def test_app_base_url_clean_prefers_configured_base_url():
    settings = Settings(_allow_missing=True)
    settings.app_base_url = "https://api.example.com/"
    settings.frontend_origin = "https://frontend.example.com/"

    assert settings.app_base_url_clean == "https://api.example.com"


def test_namespace_view_updates_and_deletes_its_own_slots():
    parent = SimpleNamespace()
    view = _NamespaceView(parent, DatabaseSettings)

    view.delegated_attribute = "delegated"
    assert parent.delegated_attribute == "delegated"

    view._mixin_cls = SecuritySettings
    assert view._mixin_cls is SecuritySettings

    del view._mixin_cls
    # A missing delegated attribute is intentionally ignored by __delattr__.
    del view.missing_attribute
