"""Closure tests for file-scanner error and upload-stream branches."""

from __future__ import annotations

import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.services.file_scanner import (
    FileScannerUnavailableError,
    _check_clamd_health,
    _create_clamd_client,
    _scan_with_clamd_stream,
    _scanner_size_limit_bytes,
    _ScanResult,
    scan_for_malware,
)


def test_create_network_clamd_client_failure_is_domain_error():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_timeout = 1.0
        mock_settings.event_file_scanner_host = "127.0.0.1"
        mock_settings.event_file_scanner_port = 3310
        with patch("clamd.ClamdNetworkSocket", side_effect=OSError("offline")):
            with pytest.raises(FileScannerUnavailableError, match="unable to connect"):
                _create_clamd_client()


def test_create_clamd_client_reports_missing_dependency():
    with patch.dict(sys.modules, {"clamd": None}):
        with pytest.raises(FileScannerUnavailableError, match="python-clamd"):
            _create_clamd_client()


def test_scanner_size_limit_invalid_value_is_disabled():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_max_size_mb = "not-a-number"

        assert _scanner_size_limit_bytes() == 0


def test_scan_stream_preserves_domain_error_and_wraps_client_error():
    with patch(
        "app.services.file_scanner._create_clamd_client",
        side_effect=FileScannerUnavailableError("not configured"),
    ):
        with pytest.raises(FileScannerUnavailableError, match="not configured"):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

    client = MagicMock()
    client.instream.side_effect = RuntimeError("socket closed")
    with patch("app.services.file_scanner._create_clamd_client", return_value=client):
        with pytest.raises(FileScannerUnavailableError, match="clamd scan failed"):
            _scan_with_clamd_stream(io.BytesIO(b"data"))


def test_check_health_returns_on_pong_and_wraps_client_error():
    client = MagicMock()
    client.ping.return_value = "pong"
    with patch("app.services.file_scanner._create_clamd_client", return_value=client):
        _check_clamd_health()

    client.ping.side_effect = RuntimeError("socket closed")
    with patch("app.services.file_scanner._create_clamd_client", return_value=client):
        with pytest.raises(
            FileScannerUnavailableError, match="clamd health check failed"
        ):
            _check_clamd_health()


@pytest.mark.anyio
async def test_scan_for_malware_upload_zero_size_returns_before_scan():
    upload = UploadFile(file=io.BytesIO(), filename="empty.bin")

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        await scan_for_malware(upload, size_bytes=0)


@pytest.mark.anyio
async def test_scan_for_malware_ignores_unsupported_payload_type():
    await scan_for_malware(object())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_scan_for_malware_uses_stream_scanner_for_upload():
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="payload.bin")
    result = _ScanResult(signature=None, duration=0.01, bytes_scanned=7)

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_max_size_mb = 0
        mock_settings.event_file_scanner_allow_on_unavailable = False
        mock_settings.environment = "testing"
        with patch(
            "app.services.file_scanner._scan_upload_with_clamd",
            new=AsyncMock(return_value=result),
        ) as mock_scan:
            await scan_for_malware(upload, size_bytes=7)

        mock_scan.assert_awaited_once_with(upload, size_limit=0)


@pytest.mark.anyio
async def test_infected_scan_without_quarantine_handler_raises():
    result = _ScanResult(signature="EICAR", duration=0.01, bytes_scanned=5)

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_max_size_mb = 0
        mock_settings.event_file_scanner_allow_on_unavailable = False
        mock_settings.environment = "testing"
        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            new=AsyncMock(return_value=result),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await scan_for_malware(b"data")

    assert exc_info.value.status_code == 400
