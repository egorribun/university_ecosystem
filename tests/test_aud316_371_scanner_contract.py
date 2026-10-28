"""AUD-316/371: operator configuration and fail-closed file scanning."""

from __future__ import annotations

import io
import secrets
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import HTTPException, UploadFile

from app.core import profiling, spicedb
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.core.config import Settings
from app.services import file_scanner
from app.services.chat import attachment_service
from tests.test_aud467_settings_integration_environment import (
    _clear_secret_file_inputs,
    _valid_production_settings,
)

ROOT = Path(__file__).resolve().parents[1]


class _SettingsWithRetiredScannerFlag(Settings):
    """Detect accidental restoration of the retired input on a real settings model."""

    event_file_scanner_allow_on_unavailable: bool = False


def _settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    settings_type: type[Settings],
) -> Settings:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("EVENT_FILE_SCANNER_ENABLED", "true")
    monkeypatch.setenv("EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE", "true")
    monkeypatch.setenv("CI", "false")
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    _clear_secret_file_inputs(monkeypatch)

    values: dict[str, Any] = {"_env_file": None}
    if environment in {"production", "staging"}:
        values.update(_valid_production_settings())
        del values["event_file_scanner_enabled"]
        values["elasticsearch_password"] = secrets.token_urlsafe(32)
    else:
        values["_allow_missing"] = True
    return settings_type(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment", ["development", "testing", "staging", "production"]
)
@pytest.mark.parametrize("upload", [False, True], ids=["bytes", "upload"])
@pytest.mark.parametrize(
    "settings_type",
    [Settings, _SettingsWithRetiredScannerFlag],
    ids=["actual", "retired-field"],
)
async def test_scanner_outage_and_open_circuit_never_accept_unscanned_payloads(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    upload: bool,
    settings_type: type[Settings],
) -> None:
    """Actual env input and a retired-field regression both remain fail-closed."""
    settings = _settings_from_environment(monkeypatch, environment, settings_type)
    assert settings.event_file_scanner_enabled is True
    if settings_type is Settings:
        assert not hasattr(settings, "event_file_scanner_allow_on_unavailable")
    else:
        assert settings.event_file_scanner_allow_on_unavailable is True  # type: ignore[attr-defined]

    breaker = CircuitBreaker(
        "aud371-test-scanner",
        config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=60),
    )
    calls = 0

    class UnavailableClient:
        def instream(self, _stream: object) -> None:
            nonlocal calls
            calls += 1
            raise OSError("synthetic scanner outage")

    async def unavailable_connection(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        raise OSError("synthetic scanner outage")

    monkeypatch.setattr(file_scanner, "settings", settings)
    monkeypatch.setattr(file_scanner, "_clamav_circuit_breaker", breaker)
    monkeypatch.setattr(file_scanner, "_create_clamd_client", UnavailableClient)
    monkeypatch.setattr(file_scanner.asyncio, "open_connection", unavailable_connection)

    for _ in range(4):
        payload: bytes | UploadFile = b"synthetic document"
        if upload:
            payload = UploadFile(file=io.BytesIO(payload), filename="document.txt")
        try:
            with pytest.raises(HTTPException) as exc_info:
                await file_scanner.scan_for_malware(payload)
            assert exc_info.value.status_code == 503
        finally:
            if isinstance(payload, UploadFile):
                await payload.close()

    assert calls == 3  # Fourth request was rejected by the actual open breaker.
    assert breaker.metrics.rejected_calls == 1


@pytest.mark.asyncio
async def test_chat_upload_never_reaches_storage_during_a_scanner_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_from_environment(
        monkeypatch, "testing", _SettingsWithRetiredScannerFlag
    )
    breaker = CircuitBreaker(
        "aud371-attachment-scanner",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=60),
    )
    calls = 0

    async def unavailable_connection(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        raise OSError("synthetic scanner outage")

    persist = AsyncMock()
    monkeypatch.setattr(file_scanner, "settings", settings)
    monkeypatch.setattr(file_scanner, "_clamav_circuit_breaker", breaker)
    monkeypatch.setattr(file_scanner.asyncio, "open_connection", unavailable_connection)
    monkeypatch.setattr(attachment_service, "save_attachment", persist)

    for _ in range(2):
        upload = UploadFile(file=io.BytesIO(b"synthetic document"), filename="note.txt")
        try:
            with pytest.raises(HTTPException) as exc_info:
                await attachment_service.ChatAttachmentService().process_upload(
                    upload, uuid.uuid4(), locale="en"
                )
            assert exc_info.value.status_code == 503
        finally:
            await upload.close()

    assert calls == 1
    assert breaker.metrics.rejected_calls == 1
    persist.assert_not_awaited()


def test_env_example_identifies_actual_spicedb_and_profiling_consumers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assignments = {
        line.split("=", 1)[0]
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert {
        "SPICEDB_ENDPOINT",
        "ENABLE_PROFILING",
        "PYROSCOPE_SERVER_ADDRESS",
    } <= assignments
    assert (
        not {
            "SPICEDB_HOST",
            "SPICEDB_PORT",
            "SPICEDB_PG_SSLMODE",
            "EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE",
        }
        & assignments
    )
    assert "Profiling reads only the backend process environment" in example
    assert "Compose passes its backend env_file entries" in example

    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.delenv("SPICEDB_ENDPOINT", raising=False)
    monkeypatch.delenv("ENABLE_PROFILING", raising=False)
    monkeypatch.delenv("PYROSCOPE_SERVER_ADDRESS", raising=False)
    dotenv = tmp_path / "example.env"
    dotenv.write_text(
        "SPICEDB_ENDPOINT=spicedb.synthetic.invalid:1234\n"
        "ENABLE_PROFILING=true\n"
        "PYROSCOPE_SERVER_ADDRESS=http://profiler.synthetic.invalid:4040\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=dotenv, _allow_missing=True)
    monkeypatch.setattr(spicedb, "settings", settings)
    assert spicedb.SpiceDBClient()._endpoint == "spicedb.synthetic.invalid:1234"
    assert isinstance(profiling.get_profiler(), profiling.NoOpProfiler)

    monkeypatch.setenv("ENABLE_PROFILING", "true")
    monkeypatch.setenv(
        "PYROSCOPE_SERVER_ADDRESS", "http://profiler.synthetic.invalid:4040"
    )
    profiler = profiling.get_profiler()
    assert isinstance(profiler, profiling.PyroscopeProfiler)
    assert profiler.server_address == "http://profiler.synthetic.invalid:4040"


@pytest.mark.parametrize(
    ("compose_name", "env_file_name"),
    [("docker-compose.yml", ".env"), ("docker-compose.full.yml", ".env.docker")],
)
def test_compose_backend_passes_its_env_file_to_profiler(
    compose_name: str, env_file_name: str
) -> None:
    source = (ROOT / compose_name).read_text(encoding="utf-8")
    compose = yaml.safe_load(source.replace("!override", "").replace("!reset", ""))
    backend = compose["services"]["backend"]
    env_files = [
        item["path"] if isinstance(item, dict) else item for item in backend["env_file"]
    ]

    assert env_file_name in env_files
    assert not {"ENABLE_PROFILING", "PYROSCOPE_SERVER_ADDRESS"} & set(
        backend.get("environment", {})
    )
