"""AUD-164: the staging and production HTTP API must name its trusted proxies."""

from __future__ import annotations

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.test_aud467_settings_integration_environment import (
    _valid_production_settings,
)


def _settings(environment: str, trusted_proxies: str, role: str = "api") -> Settings:
    settings = Settings(_allow_missing=True)
    settings.environment = environment
    settings.app_process_role = role
    settings.trusted_proxies = trusted_proxies
    return settings


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud164_empty_trusted_proxies_fail_closed_for_the_http_api(
    environment: str,
) -> None:
    settings = _settings(environment, "")

    with pytest.raises(ValueError, match="TRUSTED_PROXIES must list"):
        settings._require_explicit_trusted_proxies()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud164_explicit_gateway_and_edge_cidrs_are_accepted(environment: str) -> None:
    settings = _settings(environment, "172.23.0.20/32, 172.23.0.30/32")

    assert settings._require_explicit_trusted_proxies() is settings
    assert settings.trusted_proxies_list == ["172.23.0.20/32", "172.23.0.30/32"]


@pytest.mark.parametrize("role", ["outbox-worker", "notifications-worker"])
def test_aud164_workers_without_client_traffic_do_not_need_peers(role: str) -> None:
    settings = _settings("production", "", role=role)

    assert settings._require_explicit_trusted_proxies() is settings
    assert settings.trusted_proxies_list == []


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_aud164_local_environments_keep_the_no_trust_default(environment: str) -> None:
    settings = _settings(environment, "")

    assert settings._require_explicit_trusted_proxies() is settings
    assert settings.trusted_proxies_list == []


def _constructed_production_values() -> dict[str, object]:
    values = _valid_production_settings()
    values["environment"] = "production"
    values["elasticsearch_password"] = secrets.token_urlsafe(32)
    values["_env_file"] = None
    return values


def test_aud164_construction_rejects_production_without_trusted_proxies() -> None:
    values = _constructed_production_values()
    values.pop("trusted_proxies")

    with pytest.raises(ValidationError, match="TRUSTED_PROXIES must list"):
        Settings(**values)


def test_aud164_construction_accepts_production_with_explicit_proxies() -> None:
    settings = Settings(**_constructed_production_values())

    assert settings.trusted_proxies_list == ["10.0.0.0/8"]
