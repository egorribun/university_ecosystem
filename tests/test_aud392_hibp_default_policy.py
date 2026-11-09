"""AUD-392: leaked-password screening is on by default in deployed environments."""

from __future__ import annotations

import secrets

import pytest

from app.core.config import Settings
from tests.test_aud467_settings_integration_environment import (
    _valid_production_settings,
)


def _settings(environment: str) -> Settings:
    settings = Settings(_allow_missing=True)
    settings.environment = environment
    return settings


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud392_unset_hibp_flag_resolves_to_enabled_when_deployed(
    environment: str,
) -> None:
    settings = _settings(environment)

    assert settings._enable_hibp_screening_in_deployed_environments() is settings
    assert settings.password_hibp_check_enabled is True


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud392_explicit_disable_is_rejected_when_deployed(environment: str) -> None:
    settings = _settings(environment)
    settings.password_hibp_check_enabled = False

    with pytest.raises(ValueError, match="PASSWORD_HIBP_CHECK_ENABLED must be true"):
        settings._enable_hibp_screening_in_deployed_environments()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud392_explicit_enable_is_kept_when_deployed(environment: str) -> None:
    settings = _settings(environment)
    settings.password_hibp_check_enabled = True

    assert settings._enable_hibp_screening_in_deployed_environments() is settings
    assert settings.password_hibp_check_enabled is True


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_aud392_local_environments_keep_the_opt_in_default(environment: str) -> None:
    settings = _settings(environment)

    assert settings._enable_hibp_screening_in_deployed_environments() is settings
    assert settings.password_hibp_check_enabled is False


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud392_fail_open_default_stays_closed(environment: str) -> None:
    settings = _settings(environment)

    settings._enable_hibp_screening_in_deployed_environments()

    assert settings.password_hibp_fail_open is False


def test_aud392_construction_enables_hibp_by_default_in_production() -> None:
    values = _valid_production_settings()
    values["environment"] = "production"
    values["elasticsearch_password"] = secrets.token_urlsafe(32)
    values["_env_file"] = None

    settings = Settings(**values)

    assert settings.password_hibp_check_enabled is True
    assert settings.password_hibp_fail_open is False
