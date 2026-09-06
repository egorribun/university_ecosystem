"""Focused closure tests for the base settings helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

import app.core.config.base as base


def _missing_error(*locations: tuple[object, ...]) -> ValidationError:
    return ValidationError.from_exception_data(
        "BaseSettings",
        [{"type": "missing", "loc": location, "input": None} for location in locations],
    )


def test_resolve_env_file_handles_missing_example_and_empty_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    assert base._resolve_env_file(tmp_path) is None

    monkeypatch.setenv("ENV_FILE_PATH", "")
    assert base._resolve_env_file(tmp_path) is None

    monkeypatch.setenv("ENV_FILE_PATH", str(tmp_path / "missing.env"))
    assert base._resolve_env_file(tmp_path) is None

    # An empty optional override behaves like an unset override and must not
    # turn Path("") into the process working directory.
    monkeypatch.setenv("ENV_EXAMPLE_PATH", "")
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    candidate = tmp_path / ".env"
    candidate.write_text("DATABASE_URL=sqlite\n", encoding="utf-8")
    assert base._resolve_env_file(tmp_path) == candidate


def test_resolve_env_file_warns_for_explicit_example_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    example = tmp_path / "example.env"
    candidate = tmp_path / "candidate.env"
    example.write_bytes(b"DATABASE_URL=example\n")
    candidate.write_bytes(example.read_bytes())
    monkeypatch.setenv("ENV_EXAMPLE_PATH", str(example))
    monkeypatch.setenv("ENV_FILE_PATH", str(candidate))

    with caplog.at_level(logging.WARNING):
        assert base._resolve_env_file(tmp_path) == candidate

    assert "identical" in caplog.text
    messages = [
        str(getattr(record, "msg", ""))
        + " "
        + str(getattr(record, "msg", {}).get("message", ""))
        if isinstance(getattr(record, "msg", None), dict)
        else record.getMessage()
        for record in caplog.records
    ]
    assert any(str(candidate) in message for message in messages)
    assert any(str(example) in message for message in messages)


def test_resolve_env_file_accepts_explicit_candidate_with_real_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = tmp_path / "example.env"
    candidate = tmp_path / "candidate.env"
    example.write_bytes(b"example")
    candidate.write_bytes(b"real-value")
    monkeypatch.setenv("ENV_EXAMPLE_PATH", str(example))
    monkeypatch.setenv("ENV_FILE_PATH", str(candidate))

    assert base._resolve_env_file(tmp_path) == candidate


def test_resolve_env_file_accepts_explicit_candidate_without_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = tmp_path / "candidate.env"
    candidate.write_bytes(b"real-value")
    monkeypatch.setenv("ENV_EXAMPLE_PATH", str(tmp_path / "missing.example"))
    monkeypatch.setenv("ENV_FILE_PATH", str(candidate))

    assert base._resolve_env_file(tmp_path) == candidate


def test_resolve_env_file_handles_unreadable_explicit_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = tmp_path / "example.env"
    candidate = tmp_path / "candidate.env"
    example.write_bytes(b"example")
    candidate.write_bytes(b"candidate")
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == candidate:
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setenv("ENV_EXAMPLE_PATH", str(example))
    monkeypatch.setenv("ENV_FILE_PATH", str(candidate))

    assert base._resolve_env_file(tmp_path) == candidate


@pytest.mark.parametrize("candidate_name", [".env", ".env.local"])
def test_resolve_env_file_finds_default_candidates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, candidate_name: str
) -> None:
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)
    candidate = tmp_path / candidate_name
    candidate.write_text("DATABASE_URL=sqlite\n", encoding="utf-8")

    assert base._resolve_env_file(tmp_path) == candidate


def test_resolve_env_file_warns_for_default_env_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    example = tmp_path / ".env.example"
    candidate = tmp_path / ".env"
    content = b"SECRET_KEY=example\n"
    example.write_bytes(content)
    candidate.write_bytes(content)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)

    with caplog.at_level(logging.WARNING):
        assert base._resolve_env_file(tmp_path) == candidate

    assert "identical" in caplog.text
    messages = [
        str(getattr(record, "msg", ""))
        + " "
        + str(getattr(record, "msg", {}).get("message", ""))
        if isinstance(getattr(record, "msg", None), dict)
        else record.getMessage()
        for record in caplog.records
    ]
    assert any(str(candidate) in message for message in messages)
    assert any(str(example) in message for message in messages)


def test_resolve_env_file_default_warning_keeps_both_path_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The warning must identify the concrete file that needs remediation."""
    example = tmp_path / ".env.example"
    candidate = tmp_path / ".env"
    content = b"SECRET_KEY=example\n"
    example.write_bytes(content)
    candidate.write_bytes(content)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)

    with patch.object(base._logger, "warning") as warning:
        assert base._resolve_env_file(tmp_path) == candidate

    warning.assert_called_once()
    assert warning.call_args is not None
    args = warning.call_args.args
    assert args[1] == candidate
    assert args[2] == example


def test_resolve_env_file_accepts_default_env_with_real_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = tmp_path / ".env.example"
    candidate = tmp_path / ".env"
    example.write_bytes(b"example")
    candidate.write_bytes(b"real-value")
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)

    assert base._resolve_env_file(tmp_path) == candidate


def test_resolve_env_file_handles_unreadable_default_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = tmp_path / ".env.example"
    candidate = tmp_path / ".env"
    example.write_bytes(b"example")
    candidate.write_bytes(b"candidate")
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == candidate:
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("ENV_EXAMPLE_PATH", raising=False)

    assert base._resolve_env_file(tmp_path) == candidate


def test_base_settings_formats_unusual_missing_locations() -> None:
    error = _missing_error((), (1,), ("SECRET_KEY",))
    with patch.object(BaseSettings, "__init__", side_effect=error):
        with pytest.raises(
            RuntimeError, match="Missing required environment variables"
        ):
            base.BaseAppSettings()


def test_base_settings_reraises_non_missing_validation_errors() -> None:
    class TypedSettings(base.BaseAppSettings):
        count: int
        model_config = SettingsConfigDict(env_file=None)

    with pytest.raises(ValidationError):
        TypedSettings(count="not-an-integer")


def test_development_fallback_fields_normalize_non_tuple_storage() -> None:
    settings = base.BaseAppSettings.model_construct()
    object.__setattr__(settings, "_development_fallback_fields", ["DATABASE_URL"])

    assert settings.development_fallback_fields == ("DATABASE_URL",)
    assert settings.has_development_fallbacks is True

    object.__setattr__(settings, "_development_fallback_fields", ("SECRET_KEY",))
    assert settings.development_fallback_fields == ("SECRET_KEY",)


def test_validation_helpers_reject_invalid_values() -> None:
    assert base._coerce_int_list(["1", "not-an-int"]) == [1]

    with pytest.raises(ValueError, match="must not be empty"):
        base._validate_non_empty("  ", label="value")
    with pytest.raises(ValueError, match="greater than zero"):
        base._validate_positive_int(0, label="count")
    with pytest.raises(ValueError, match="zero or positive"):
        base._validate_non_negative_int(-1, label="offset")
    with pytest.raises(ValueError, match="greater than zero"):
        base._validate_positive_float(0.0, label="timeout")


def test_load_file_secret_raises_for_unreadable_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "missing-secret"
    monkeypatch.setenv("SECRET_KEY_FILE", str(path))

    with pytest.raises(
        ValueError, match="SECRET_KEY_FILE points to a non-readable file"
    ):
        base._load_file_secret("SECRET_KEY_FILE", "fallback")


def test_development_defaults_are_blocked_when_env_file_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with patch.object(base, "_ENV_FILE", tmp_path / ".env"):
        assert base._should_allow_development_defaults() is False


def test_development_defaults_cover_production_ci_and_missing_field_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with patch.object(base, "_ENV_FILE", None):
        assert base._should_allow_development_defaults() is False

    monkeypatch.setenv("ENVIRONMENT", "unknown")
    with patch.object(base, "_ENV_FILE", None):
        assert base._should_allow_development_defaults() is False

    monkeypatch.setenv("ENVIRONMENT", "development")
    with patch.object(base, "_ENV_FILE", None):
        assert base._should_allow_development_defaults(["DATABASE_URL"]) is True
        assert base._should_allow_development_defaults(["UNSUPPORTED"]) is False


def test_development_fallbacks_fill_database_and_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FallbackSettings(base.BaseAppSettings):
        database_url: str
        secret_key: str
        model_config = SettingsConfigDict(env_file=None)

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    with patch.object(base, "_ENV_FILE", None):
        settings = FallbackSettings(_allow_missing=True)

    assert settings.database_url == "sqlite+aiosqlite:///./dev.db"
    assert settings.secret_key
    assert settings.has_development_fallbacks is True


def test_development_fallbacks_reject_unknown_required_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnsupportedSettings(base.BaseAppSettings):
        unsupported: str
        model_config = SettingsConfigDict(env_file=None)

    monkeypatch.delenv("UNSUPPORTED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    with patch.object(base, "_ENV_FILE", None):
        with pytest.raises(RuntimeError, match="UNSUPPORTED"):
            UnsupportedSettings(_allow_missing=True)


def test_development_defaults_generic_secret_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with patch.object(base, "_ENV_FILE", None):
        assert base._should_allow_development_defaults() is True

    monkeypatch.setenv("SECRET_KEY", "configured")
    with patch.object(base, "_ENV_FILE", None):
        assert base._should_allow_development_defaults() is False
