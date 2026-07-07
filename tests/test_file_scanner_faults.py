from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.circuit_breaker import CircuitBreakerOpenError
from app.services.file_scanner import (
    FileScannerPayloadTooLarge,
    FileScannerUnavailableError,
    _check_clamd_health,
    _scan_upload_with_clamd,
    _scanner_duration_limit_seconds,
    _UploadStream,
    check_file_scanner_health,
    scan_for_malware,
)


def test_check_clamd_health_failures() -> None:
    # 1. Raise FileScannerUnavailableError from client creation
    with patch("app.services.file_scanner._create_clamd_client") as mock_create:
        mock_create.side_effect = FileScannerUnavailableError("not found")
        with pytest.raises(FileScannerUnavailableError, match="not found"):
            _check_clamd_health()

    # 2. Unexpected health response
    mock_client = MagicMock()
    mock_client.ping.return_value = "NOT-PONG"
    with patch(
        "app.services.file_scanner._create_clamd_client", return_value=mock_client
    ):
        with pytest.raises(
            FileScannerUnavailableError, match="unexpected clamd health response"
        ):
            _check_clamd_health()


def test_scanner_duration_limit_seconds_exceptions() -> None:
    with patch("app.services.file_scanner.settings") as mock_settings:
        # Raises ValueError on float conversion
        mock_settings.event_file_scanner_max_duration_sec = "invalid"
        assert _scanner_duration_limit_seconds() == 0.0

        # Negative value returns 0.0
        mock_settings.event_file_scanner_max_duration_sec = -10.0
        assert _scanner_duration_limit_seconds() == 0.0


def test_upload_stream_empty_read() -> None:
    wrapped = io.BytesIO(b"")
    stream = _UploadStream(wrapped, limit=100)
    # Reading empty stream triggers early return
    assert stream.read() == b""


@pytest.mark.asyncio
async def test_scan_upload_with_clamd_exceptions() -> None:
    wrapped = io.BytesIO(b"payload content")
    stream = _UploadStream(wrapped, limit=100)

    # 1. Trigger TimeoutError
    with patch("asyncio.open_connection") as mock_open:
        mock_open.side_effect = TimeoutError("timeout")

        with pytest.raises(FileScannerUnavailableError, match="clamd scan timed out"):
            await _scan_upload_with_clamd(stream, size_limit=100)

    # 2. Trigger general exception
    with patch("asyncio.open_connection") as mock_open:
        mock_open.side_effect = RuntimeError("network fail")

        with pytest.raises(FileScannerUnavailableError, match="clamd scan failed"):
            await _scan_upload_with_clamd(stream, size_limit=100)


@pytest.mark.asyncio
async def test_check_file_scanner_health_disabled() -> None:
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = False
        # Should return early without exception
        await check_file_scanner_health()


@pytest.mark.asyncio
async def test_scan_for_malware_scenarios() -> None:
    # 1. Trigger FileScannerPayloadTooLarge (returns HTTP 413)
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_allow_on_unavailable = False
        mock_settings.environment = "testing"

        with patch("app.services.file_scanner._clamav_circuit_breaker") as mock_cb:
            mock_cb.__aenter__.return_value = MagicMock()
            with patch("app.services.file_scanner._scan_bytes_with_clamd") as mock_scan:
                mock_scan.side_effect = FileScannerPayloadTooLarge(
                    size_bytes=200, limit_bytes=100
                )

                with pytest.raises(HTTPException) as exc_info:
                    await scan_for_malware(b"data")
                assert exc_info.value.status_code == 413

    # 2. Trigger FileScannerUnavailableError (returns HTTP 503)
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_allow_on_unavailable = False
        mock_settings.environment = "testing"

        with patch("app.services.file_scanner._clamav_circuit_breaker") as mock_cb:
            mock_cb.__aenter__.return_value = MagicMock()
            with patch("app.services.file_scanner._scan_bytes_with_clamd") as mock_scan:
                mock_scan.side_effect = FileScannerUnavailableError("unavailable")

                with pytest.raises(HTTPException) as exc_info:
                    await scan_for_malware(b"data")
                assert exc_info.value.status_code == 503

    # 3. Trigger CircuitBreakerOpenError with allow_on_unavailable = False (returns HTTP 503)
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_allow_on_unavailable = False
        mock_settings.environment = "testing"

        with patch("app.services.file_scanner._clamav_circuit_breaker") as mock_cb:
            mock_cb.__aenter__.return_value = MagicMock()
            with patch("app.services.file_scanner._scan_bytes_with_clamd") as mock_scan:
                mock_scan.side_effect = CircuitBreakerOpenError(
                    "clamav", remaining_seconds=5.0, failure_count=3
                )

                with pytest.raises(HTTPException) as exc_info:
                    await scan_for_malware(b"data")
                assert exc_info.value.status_code == 503

    # 4. Trigger CircuitBreakerOpenError with allow_on_unavailable = True (fail open cleanly)
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_allow_on_unavailable = True
        mock_settings.environment = "testing"

        with patch("app.services.file_scanner._clamav_circuit_breaker") as mock_cb:
            mock_cb.__aenter__.return_value = MagicMock()
            with patch("app.services.file_scanner._scan_bytes_with_clamd") as mock_scan:
                mock_scan.side_effect = CircuitBreakerOpenError(
                    "clamav", remaining_seconds=5.0, failure_count=3
                )

                # Should not raise exception
                await scan_for_malware(b"data")
