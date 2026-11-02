"""Database-only source view for model metadata and Alembic bootstrap.

This module does not instantiate runtime Settings, create engines, or consume
application encryption/signing keys. A recorded development default is metadata
provenance, not authorization to execute a migration against that database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core.logging import get_logger
from app.core.settings_sources import (
    _DEVELOPMENT_ENVIRONMENTS,
    _DEVELOPMENT_FALLBACKS,
    _load_file_secret,
    resolve_env_file,
    should_allow_development_defaults,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_logger = get_logger(__name__)


class _DatabaseInput(BaseSettings):
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _prepare_database_file(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        if "DATABASE_URL_FILE" not in os.environ:
            return values
        resolved = dict(values)
        resolved.setdefault("database_url", "")
        return resolved

    @field_validator("database_url", mode="before")
    @classmethod
    def _load_database_file(cls, value: str | None) -> str | None:
        return _load_file_secret("DATABASE_URL_FILE", value)


@dataclass(frozen=True)
class MigrationSettings:
    database_url: str | None = field(repr=False)
    source: Literal["configured", "development-default", "missing"]

    @property
    def development_fallback_fields(self) -> tuple[str, ...]:
        return ("database_url",) if self.source == "development-default" else ()

    @property
    def has_development_fallbacks(self) -> bool:
        return bool(self.development_fallback_fields)


def _parse_database_url(value: str) -> URL:
    """Validate URL syntax without echoing credential-bearing input fragments."""
    try:
        return make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("Invalid database URL configuration") from None


def load_migration_settings() -> MigrationSettings:
    """Resolve only the database source with the runtime source conventions."""
    env_file = resolve_env_file(_PROJECT_ROOT, logger=_logger)
    inputs = _DatabaseInput(_env_file=env_file)
    if inputs.database_url is not None:
        # An explicitly empty field is supplied, not a missing-field fallback.
        # Other malformed URLs fail before any ini/default fallback is considered.
        if inputs.database_url:
            _parse_database_url(inputs.database_url)
        return MigrationSettings(inputs.database_url, "configured")
    if should_allow_development_defaults(("DATABASE_URL",), env_file=env_file):
        return MigrationSettings(
            _DEVELOPMENT_FALLBACKS["database_url"], "development-default"
        )
    return MigrationSettings(None, "missing")


def resolve_migration_url(source: MigrationSettings, *, ini_url: str | None) -> str:
    """Select an explicit source before the provenance-marked local default."""
    if source.database_url and not source.has_development_fallbacks:
        _parse_database_url(source.database_url)
        return source.database_url
    if ini_url:
        _parse_database_url(ini_url)
        return ini_url
    if source.database_url:
        _parse_database_url(source.database_url)
        return source.database_url
    raise RuntimeError("Database URL is not configured for Alembic")


def should_skip_development_migration(
    *,
    development_fallback_fields: tuple[str, ...],
    environment: str,
    explicit_target: bool,
) -> bool:
    """Retain only the documented no-target local development skip."""
    return (
        "database_url" in development_fallback_fields
        and environment.strip().lower() in _DEVELOPMENT_ENVIRONMENTS
        and not explicit_target
    )


def database_dialect_for_models() -> str:
    """Keep runtime dialect declarations without importing runtime Settings.

    The ordinary runtime continues to validate its own settings. Metadata-only
    callers may have no configured URL (for example an Alembic ini target);
    their canonical declaration is projected on a clone for the actual target.
    The established local runtime SQLite fallback remains explicitly recorded.
    """
    database_url = load_migration_settings().database_url
    if database_url is None or database_url == "":
        return "postgresql"
    return _parse_database_url(database_url).get_backend_name()
