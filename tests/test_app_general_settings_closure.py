"""Focused tests for AppGeneralSettings validators and derived properties."""

import pytest
from pydantic import ValidationError

from app.core.config.app_gen import AppGeneralSettings


def test_environment_is_normalized_and_development_is_cached():
    settings = AppGeneralSettings(_allow_missing=True, environment="  TEST ")

    assert settings.environment == "test"
    assert settings.is_development is True
    assert settings.is_development is True


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError, match="Unknown ENVIRONMENT value"):
        AppGeneralSettings(_allow_missing=True, environment="prod")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("", False),
        ("yes", True),
    ],
)
def test_auto_create_schema_accepts_string_switches(raw: str, expected: bool):
    settings = AppGeneralSettings(
        _allow_missing=True,
        environment="development",
        auto_create_schema=raw,
    )

    assert settings.auto_create_schema is expected


def test_auto_create_schema_accepts_boolean_and_uses_environment_default():
    assert (
        AppGeneralSettings(
            _allow_missing=True, environment="development", auto_create_schema=True
        ).auto_create_schema
        is True
    )
    assert (
        AppGeneralSettings(
            _allow_missing=True, environment="production", auto_create_schema=False
        ).auto_create_schema
        is False
    )
    assert (
        AppGeneralSettings(
            _allow_missing=True, environment="development"
        ).auto_create_schema
        is True
    )
    assert (
        AppGeneralSettings(
            _allow_missing=True, environment="production"
        ).auto_create_schema
        is False
    )


def test_metrics_allowlist_entries_coerces_strings_and_iterables():
    assert AppGeneralSettings(
        _allow_missing=True, metrics_allowlist=" 10, /health, , /ready "
    ).metrics_allowlist_entries == ["10", "/health", "/ready"]
    assert AppGeneralSettings(
        _allow_missing=True, metrics_allowlist=[" /metrics ", " 42 ", ""]
    ).metrics_allowlist_entries == ["/metrics", "42"]
    assert (
        AppGeneralSettings(
            _allow_missing=True, metrics_allowlist=""
        ).metrics_allowlist_entries
        == []
    )
