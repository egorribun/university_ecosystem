"""Database-source precedence for configuration-free migration metadata."""

from __future__ import annotations

import os
import secrets
import traceback
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import migration_settings as migration


@pytest.fixture(autouse=True)
def clean_database_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    controlled = {
        "database_url",
        "database_url_file",
        "environment",
        "ci",
        "github_actions",
        "env_file_path",
        "env_example_path",
    }
    for name in tuple(os.environ):
        if name.casefold() in controlled:
            monkeypatch.delenv(name)
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.setenv("ENVIRONMENT", "production")


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_missing_protected_database_is_not_an_execution_target(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    source = migration.load_migration_settings()
    assert source == migration.MigrationSettings(None, "missing")
    assert source.development_fallback_fields == ()
    assert not source.has_development_fallbacks
    assert migration.database_dialect_for_models() == "postgresql"


@pytest.mark.parametrize(
    "environment", ["dev", "development", "local", "test", "testing"]
)
def test_existing_runtime_development_dialect_is_preserved(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    source = migration.load_migration_settings()
    assert source.database_url == "sqlite+aiosqlite:///./dev.db"
    assert source.source == "development-default"
    assert source.development_fallback_fields == ("database_url",)
    assert source.has_development_fallbacks
    assert migration.database_dialect_for_models() == "sqlite"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("production", "missing"), ("staging", "development-default")],
)
def test_ci_source_provenance_does_not_change_existing_runtime_policy(
    monkeypatch: pytest.MonkeyPatch, environment: str, expected: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("CI", "true")
    assert migration.load_migration_settings().source == expected


def test_plain_url_is_case_insensitive_and_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "database.env"
    dotenv.write_text("DATABASE_URL=sqlite:///dotenv.db\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE_PATH", str(dotenv))
    assert migration.load_migration_settings().database_url == "sqlite:///dotenv.db"
    monkeypatch.setenv("database_url", "postgresql://metadata.invalid/test")
    assert (
        migration.load_migration_settings().database_url
        == "postgresql://metadata.invalid/test"
    )


def test_file_url_overrides_plain_source_and_uses_the_same_dialect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mounted = tmp_path / "database-url"
    mounted.write_text("  sqlite:///mounted.db\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql://metadata.invalid/test")
    monkeypatch.setenv("DATABASE_URL_FILE", str(mounted))
    before = dict(os.environ)
    source = migration.load_migration_settings()
    assert source.database_url == "sqlite:///mounted.db"
    assert source.source == "configured"
    assert migration.database_dialect_for_models() == "sqlite"
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "kind", ["missing", "blank-path", "empty", "invalid-utf8", "malformed-url"]
)
def test_broken_database_file_never_falls_back_to_valid_plain_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    path = tmp_path / "database-file"
    if kind == "empty":
        path.write_bytes(b" \n")
    elif kind == "invalid-utf8":
        path.write_bytes(b"\xff")
    elif kind == "malformed-url":
        path.write_text("not a URL", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///must-not-win.db")
    monkeypatch.setenv("DATABASE_URL_FILE", "" if kind == "blank-path" else str(path))
    expected_error = ValueError if kind == "malformed-url" else ValidationError
    with pytest.raises(expected_error):
        migration.load_migration_settings()


def test_only_exact_uppercase_file_controls_are_recognized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "database.env"
    dotenv.write_text(
        "DATABASE_URL=sqlite:///dotenv.db\nDATABASE_URL_FILE=/must-not-open\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE_PATH", str(dotenv))
    monkeypatch.setenv("database_url_file", "/must-not-open-either")
    monkeypatch.setenv("SECRET_KEY_FILE", "/runtime-secret-must-not-be-read")
    assert migration.load_migration_settings().database_url == "sqlite:///dotenv.db"
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.setenv("env_file_path", str(dotenv))
    assert migration.load_migration_settings().database_url is None


def test_explicit_blank_is_not_a_development_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "")
    source = migration.load_migration_settings()
    assert source == migration.MigrationSettings("", "configured")
    assert not source.has_development_fallbacks
    assert migration.database_dialect_for_models() == "postgresql"


@pytest.mark.parametrize("value", [" ", "not a database URL"])
def test_malformed_plain_url_cannot_redirect_to_a_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValueError, match=r"^Invalid database URL configuration$"):
        migration.load_migration_settings()


@pytest.mark.parametrize(
    ("source", "ini", "expected"),
    [
        (
            migration.MigrationSettings("sqlite:///configured.db", "configured"),
            "sqlite:///ini.db",
            "sqlite:///configured.db",
        ),
        (
            migration.MigrationSettings(None, "missing"),
            "sqlite:///ini.db",
            "sqlite:///ini.db",
        ),
        (
            migration.MigrationSettings("", "configured"),
            "sqlite:///ini.db",
            "sqlite:///ini.db",
        ),
        (
            migration.MigrationSettings("sqlite:///dev.db", "development-default"),
            "sqlite:///ini.db",
            "sqlite:///ini.db",
        ),
    ],
)
def test_explicit_target_selection_preserves_source_provenance(source, ini, expected):
    assert migration.resolve_migration_url(source, ini_url=ini) == expected


@pytest.mark.parametrize("url", [None, ""])
def test_no_effective_target_fails_without_inventing_a_default(url):
    source = migration.MigrationSettings(
        url, "missing" if url is None else "configured"
    )
    with pytest.raises(RuntimeError, match="Database URL is not configured"):
        migration.resolve_migration_url(source, ini_url=None)


def test_database_source_repr_does_not_echo_credentials():
    token = secrets.token_urlsafe(32)
    source = migration.MigrationSettings(
        f"postgresql://user:{token}@metadata.invalid/test", "configured"
    )
    assert token not in repr(source)


@pytest.mark.parametrize("reverse", [False, True])
def test_plain_case_collision_matches_the_existing_runtime_field_source(
    monkeypatch: pytest.MonkeyPatch, reverse: bool
) -> None:
    from app.core.config.database import DatabaseSettings

    pairs = [
        ("DATABASE_URL", "sqlite:///upper.db"),
        ("database_url", "sqlite:///lower.db"),
    ]
    if reverse:
        pairs.reverse()
    for name, value in pairs:
        monkeypatch.setenv(name, value)
    expected = DatabaseSettings(_env_file=None).database_url
    assert migration.load_migration_settings().database_url == expected


def test_concrete_env_file_blocks_the_existing_local_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "incomplete.env"
    dotenv.write_text("UNRELATED_FIELD=metadata-only\n", encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ENV_FILE_PATH", str(dotenv))
    assert migration.load_migration_settings().source == "missing"


def test_database_file_prepare_leaves_non_mapping_input_unchanged() -> None:
    marker = object()
    assert migration._DatabaseInput._prepare_database_file(marker) is marker


def test_development_source_without_explicit_ini_retains_its_provenance() -> None:
    source = migration.MigrationSettings("sqlite:///dev.db", "development-default")
    with pytest.raises(RuntimeError, match="Database URL is not configured"):
        migration.resolve_migration_url(source, ini_url=None)
    assert source.source == "development-default"


@pytest.mark.parametrize("source_kind", ["plain", "file", "ini", "model"])
def test_malformed_port_diagnostics_never_echo_credential_canaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source_kind: str
) -> None:
    canary = secrets.token_urlsafe(32)
    malformed = f"postgresql://user:{canary}@metadata.invalid:not-a-port-{canary}/db"
    if source_kind == "file":
        mounted = tmp_path / "database-url"
        mounted.write_text(malformed, encoding="utf-8")
        monkeypatch.setenv("DATABASE_URL_FILE", str(mounted))
        monkeypatch.setenv("DATABASE_URL", "sqlite:///must-not-win.db")
    elif source_kind != "ini":
        monkeypatch.setenv("DATABASE_URL", malformed)

    with pytest.raises(
        ValueError, match=r"^Invalid database URL configuration$"
    ) as caught:
        if source_kind == "ini":
            migration.resolve_migration_url(
                migration.MigrationSettings(None, "missing"), ini_url=malformed
            )
        elif source_kind == "model":
            migration.database_dialect_for_models()
        else:
            migration.load_migration_settings()

    rendered = "".join(traceback.format_exception(caught.value))
    assert canary not in str(caught.value)
    assert canary not in rendered
    assert malformed not in rendered
