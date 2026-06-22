"""Unit tests for file scanner functionality."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.file_scanner import (
    FileScannerPayloadTooLarge,
    FileScannerUnavailableError,
    _scanner_size_limit_bytes,
    _UploadStream,
)


class TestUploadStream:
    """Tests for _UploadStream wrapper class."""

    def test_read_within_limit(self):
        data = b"test data here"
        wrapped = io.BytesIO(data)
        stream = _UploadStream(wrapped, limit=100)

        result = stream.read()
        assert result == data
        assert stream.bytes_scanned == len(data)

    def test_read_with_size(self):
        data = b"test data here"
        wrapped = io.BytesIO(data)
        stream = _UploadStream(wrapped, limit=100)

        result = stream.read(4)
        assert result == b"test"
        assert stream.bytes_scanned == 4

    def test_read_exceeds_limit(self):
        data = b"x" * 200
        wrapped = io.BytesIO(data)
        stream = _UploadStream(wrapped, limit=50, chunk_size=10)

        # Should raise when limit is exceeded
        with pytest.raises(FileScannerPayloadTooLarge) as exc_info:
            while True:
                chunk = stream.read(20)
                if not chunk:
                    break

        assert exc_info.value.limit_bytes == 50

    def test_read_exactly_at_limit(self):
        data = b"x" * 50
        wrapped = io.BytesIO(data)
        stream = _UploadStream(wrapped, limit=50)

        result = stream.read()
        assert result == data
        assert stream.bytes_scanned == 50


class TestFileScannerPayloadTooLarge:
    """Tests for FileScannerPayloadTooLarge exception."""

    def test_exception_message(self):
        exc = FileScannerPayloadTooLarge(1000, limit_bytes=500)

        assert exc.size_bytes == 1000
        assert exc.limit_bytes == 500
        assert "1000" in str(exc)
        assert "500" in str(exc)


class TestFileScannerUnavailableError:
    """Tests for FileScannerUnavailableError exception."""

    def test_is_exception(self):
        exc = FileScannerUnavailableError("ClamAV not running")
        assert isinstance(exc, Exception)


class TestScannerSizeLimitBytes:
    """Tests for _scanner_size_limit_bytes function."""

    @patch("app.services.file_scanner.settings")
    def test_returns_configured_limit(self, mock_settings):
        mock_settings.event_file_scanner_max_size_mb = 25.0

        result = _scanner_size_limit_bytes()

        # 25 MB = 25 * 1024 * 1024 bytes
        assert result == 25 * 1024 * 1024

    @patch("app.services.file_scanner.settings")
    def test_zero_limit_returns_zero(self, mock_settings):
        mock_settings.event_file_scanner_max_size_mb = 0.0

        result = _scanner_size_limit_bytes()
        assert result == 0

    @patch("app.services.file_scanner.settings")
    def test_fractional_mb(self, mock_settings):
        mock_settings.event_file_scanner_max_size_mb = 0.5

        result = _scanner_size_limit_bytes()

        # 0.5 MB = 0.5 * 1024 * 1024 bytes
        assert result == int(0.5 * 1024 * 1024)


# ===========================================================================
# scan_for_malware & clamd streaming/health tests
# ===========================================================================
from fastapi import HTTPException, UploadFile

from app.services.file_scanner import (
    _clamav_circuit_breaker,
    check_file_scanner_health,
    scan_for_malware,
)


@pytest.mark.anyio
async def test_scan_for_malware_disabled():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = False
        # Should return early without scanning
        await scan_for_malware(b"some-data")


@pytest.mark.anyio
async def test_scan_for_malware_empty():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_max_size_mb = 5.0
        # Empty bytes should return early
        await scan_for_malware(b"")


@pytest.mark.anyio
async def test_scan_for_malware_too_large():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_max_size_mb = 1.0  # 1MB
        # 2MB file
        with pytest.raises(HTTPException) as exc_info:
            await scan_for_malware(b"x" * (2 * 1024 * 1024), size_bytes=2 * 1024 * 1024)
        assert exc_info.value.status_code == 413


@pytest.mark.anyio
async def test_scan_for_malware_clean():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"

        from app.services.file_scanner import _ScanResult

        clean_res = _ScanResult(signature=None, duration=0.1, bytes_scanned=10)

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd", return_value=clean_res
        ) as mock_scan:
            await scan_for_malware(b"clean-data")
            mock_scan.assert_called_once_with(b"clean-data")


@pytest.mark.anyio
async def test_scan_for_malware_infected():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"

        from app.services.file_scanner import _ScanResult

        infected_res = _ScanResult(
            signature="Eicar-Signature", duration=0.1, bytes_scanned=10
        )

        quarantine_called = False

        async def mock_quarantine(payload, signature):
            nonlocal quarantine_called
            quarantine_called = True
            assert payload == b"infected-data"
            assert signature == "Eicar-Signature"

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            return_value=infected_res,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await scan_for_malware(
                    b"infected-data",
                    quarantine_payload=b"infected-data",
                    quarantine_handler=mock_quarantine,
                )
            assert exc_info.value.status_code == 400  # Bad Request (validation error)
            assert quarantine_called is True


@pytest.mark.anyio
async def test_scan_for_malware_unavailable():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"
        mock_settings.event_file_scanner_allow_on_unavailable = False

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            side_effect=FileScannerUnavailableError("clamd down"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await scan_for_malware(b"some-data")
            assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_scan_for_malware_circuit_breaker_trip():
    # Reset circuit breaker
    await _clamav_circuit_breaker.reset()

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"
        mock_settings.event_file_scanner_allow_on_unavailable = False

        # Raise 3 consecutive failures to open circuit breaker
        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            side_effect=FileScannerUnavailableError("clamd down"),
        ):
            for _ in range(3):
                with pytest.raises(HTTPException):
                    await scan_for_malware(b"some-data")

            # 4th call should fail immediately on circuit breaker open
            with patch("app.services.file_scanner.logger.warning") as mock_warn:
                with pytest.raises(HTTPException) as exc_info:
                    await scan_for_malware(b"some-data")
                assert exc_info.value.status_code == 503
                mock_warn.assert_called_once()
                assert (
                    "circuit_breaker_open"
                    in mock_warn.call_args[1]["extra"]["scan_status"]
                )

    # Reset to clean up for other tests
    await _clamav_circuit_breaker.reset()


@pytest.mark.anyio
async def test_scan_upload_with_clamd_stream_ok():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()
        # Yield clean file chunk
        mock_upload.read.side_effect = [b"chunk1", b""]

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b"stream: OK\0"

        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()

        # Mock open_connection
        with patch(
            "asyncio.open_connection", return_value=(mock_reader, mock_writer)
        ) as mock_conn:
            from app.services.file_scanner import _scan_upload_with_clamd

            res = await _scan_upload_with_clamd(mock_upload, size_limit=1000)

            mock_conn.assert_called_once_with("localhost", 3310)
            assert res.signature is None
            assert res.bytes_scanned == 6
            mock_writer.write.assert_any_call(b"zINSTREAM\0")


@pytest.mark.anyio
async def test_check_file_scanner_health():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"

        # Health check ping success
        with patch("app.services.file_scanner._check_clamd_health") as mock_ping:
            await check_file_scanner_health()
            mock_ping.assert_called_once()


# Additional missing unit tests added for 100% coverage
import logging

from app.services.file_scanner import (
    _check_clamd_health,
    _create_clamd_client,
    _log_scan_result,
    _scan_bytes_with_clamd,
    _scan_upload_with_clamd,
    _scan_with_clamd_stream,
    _scanner_duration_limit_seconds,
    _ScanResult,
)


def test_create_clamd_client_unix_socket():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = "/tmp/clamd.ctl"  # noqa: S108
        mock_settings.event_file_scanner_timeout = 10.0
        with patch("clamd.ClamdUnixSocket") as mock_unix:
            _create_clamd_client()
            mock_unix.assert_called_once_with(path="/tmp/clamd.ctl", timeout=10.0)  # noqa: S108


def test_scan_with_clamd_stream_malformed():
    mock_client = MagicMock()
    with patch(
        "app.services.file_scanner._create_clamd_client", return_value=mock_client
    ):
        # 1. Non-dict response
        mock_client.instream.return_value = "not-a-dict"
        with pytest.raises(
            FileScannerUnavailableError, match="unexpected clamd response format"
        ):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

        # 2. Dict response without stream
        mock_client.instream.return_value = {"other_key": "val"}
        with pytest.raises(
            FileScannerUnavailableError, match="unexpected clamd response format"
        ):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

        # 3. Stream value is not tuple
        mock_client.instream.return_value = {"stream": "not-a-tuple"}
        with pytest.raises(
            FileScannerUnavailableError, match="malformed clamd response"
        ):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

        # 4. Stream value is empty tuple
        mock_client.instream.return_value = {"stream": ()}
        with pytest.raises(
            FileScannerUnavailableError, match="malformed clamd response"
        ):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

        # 5. ERROR status
        mock_client.instream.return_value = {"stream": ("ERROR", "Some clamd error")}
        with pytest.raises(FileScannerUnavailableError, match="Some clamd error"):
            _scan_with_clamd_stream(io.BytesIO(b"data"))

        # 6. Unsupported status
        mock_client.instream.return_value = {"stream": ("UNKNOWN_STATUS", None)}
        with pytest.raises(
            FileScannerUnavailableError, match="unsupported clamd status"
        ):
            _scan_with_clamd_stream(io.BytesIO(b"data"))


def test_check_clamd_health_anomalies():
    mock_client = MagicMock()
    with patch(
        "app.services.file_scanner._create_clamd_client", return_value=mock_client
    ):
        # Unexpected pong value
        mock_client.ping.return_value = "NOT_PONG"
        with pytest.raises(
            FileScannerUnavailableError, match="unexpected clamd health response"
        ):
            _check_clamd_health()


def test_scanner_duration_limit():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_max_duration_sec = 0.5
        assert _scanner_duration_limit_seconds() == 0.5

    # Test warning log when duration exceeds threshold
    res = _ScanResult(signature=None, duration=1.0, bytes_scanned=100)
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_max_duration_sec = 0.5
        with patch("app.services.file_scanner.logger.log") as mock_log:
            _log_scan_result(res, "clamd")
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == logging.WARNING


def test_upload_stream_seek_tell_close():
    data = b"test data"
    wrapped = io.BytesIO(data)
    stream = _UploadStream(wrapped, limit=100)

    assert stream.tell() == 0
    stream.read(4)
    assert stream.tell() == 4

    stream.seek(0)
    assert stream.tell() == 0

    stream.close()
    assert wrapped.closed


@pytest.mark.anyio
async def test_scan_for_malware_upload_zero_size():
    mock_upload = AsyncMock(spec=UploadFile)
    # size_bytes = 0 should return early
    await scan_for_malware(mock_upload, size_bytes=0)
    mock_upload.seek.assert_not_called()


@pytest.mark.anyio
async def test_scan_for_malware_unsupported_backend():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "unsupported_backend"
        with pytest.raises(HTTPException) as exc_info:
            await scan_for_malware(b"data")
        assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_scan_for_malware_allow_on_unavailable_in_production():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_allow_on_unavailable = True
        mock_settings.environment = "production"
        with pytest.raises(
            RuntimeError,
            match="EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE must not be True in production",
        ):
            await scan_for_malware(b"data")


@pytest.mark.anyio
async def test_scan_for_malware_cb_open_allow_on_unavailable():
    from app.core.circuit_breaker import CircuitBreakerOpenError

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.event_file_scanner_allow_on_unavailable = True
        mock_settings.environment = "testing"

        # Patch the entire circuit breaker instance to raise the exception on __aenter__
        mock_cb = AsyncMock()
        mock_cb.__aenter__.side_effect = CircuitBreakerOpenError(
            "clamav", remaining_seconds=10.0, failure_count=3
        )
        with patch("app.services.file_scanner._clamav_circuit_breaker", mock_cb):
            # With allow_on_unavailable = True, this should return None (allowing the upload)
            await scan_for_malware(b"data")


@pytest.mark.anyio
async def test_scan_for_malware_quarantine_narrowed_errors():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"

        from app.services.file_scanner import _ScanResult

        infected_res = _ScanResult(
            signature="Eicar-Signature", duration=0.1, bytes_scanned=10
        )

        # Quarantine handler raises OSError/ConnectionError
        async def mock_quarantine_fail(payload, signature):
            raise OSError("Storage offline")

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            return_value=infected_res,
        ):
            with patch("app.services.file_scanner.logger.warning") as mock_warn:
                with pytest.raises(HTTPException):
                    await scan_for_malware(
                        b"infected-data",
                        quarantine_payload=b"infected-data",
                        quarantine_handler=mock_quarantine_fail,
                    )
                # Should log the warning but still propagate the infection HTTP exception
                mock_warn.assert_called_once()
                assert (
                    "Failed to quarantine infected payload" in mock_warn.call_args[0][0]
                )


@pytest.mark.anyio
async def test_scan_bytes_with_clamd_wrapper():
    from app.services.file_scanner import _ScanResult

    _ScanResult(signature=None, duration=0.05, bytes_scanned=4)
    with patch("app.services.file_scanner._scan_with_clamd_stream", return_value=None):
        result = await _scan_bytes_with_clamd(b"data")
        assert result.signature is None
        assert result.bytes_scanned == 4


@pytest.mark.anyio
async def test_scan_upload_with_clamd_unix_socket():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = "/tmp/clamd.ctl"  # noqa: S108
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()
        mock_upload.read.side_effect = [b"chunk", b""]

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b"stream: OK\0"

        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()

        # Mock open_unix_connection with an AsyncMock that returns the reader/writer tuple
        mock_open_unix = AsyncMock(return_value=(mock_reader, mock_writer))
        with patch(
            "asyncio.open_unix_connection", mock_open_unix, create=True
        ) as mock_conn:
            res = await _scan_upload_with_clamd(mock_upload, size_limit=1000)
            mock_conn.assert_called_once_with("/tmp/clamd.ctl")  # noqa: S108
            assert res.signature is None


@pytest.mark.anyio
async def test_scan_upload_with_clamd_size_limit_exceeded():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()
        # Returns chunks that will exceed the size limit
        mock_upload.read.side_effect = [b"chunk1", b"chunk2", b""]

        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            # limit is 5, first chunk is 6 bytes -> should raise FileScannerPayloadTooLarge
            with pytest.raises(FileScannerPayloadTooLarge):
                await _scan_upload_with_clamd(mock_upload, size_limit=5)
            mock_writer.close.assert_called()


@pytest.mark.anyio
async def test_scan_upload_with_clamd_close_writer_exception():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()
        mock_upload.read.side_effect = [b"chunk", b""]

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b"stream: OK\0"

        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()
        # wait_closed raises ConnectionError on closed socket
        mock_writer.wait_closed.side_effect = ConnectionError("Connection reset")

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch("app.services.file_scanner.logger.debug") as mock_debug:
                res = await _scan_upload_with_clamd(mock_upload, size_limit=1000)
                assert res.signature is None
                mock_debug.assert_called_once()
                assert (
                    "Failed to close clamd writer cleanly" in mock_debug.call_args[0][0]
                )


@pytest.mark.anyio
async def test_scan_upload_with_clamd_empty_response():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()
        mock_upload.read.side_effect = [b"chunk", b""]

        mock_reader = AsyncMock()
        mock_reader.read.return_value = b""  # Empty response

        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with pytest.raises(
                FileScannerUnavailableError, match="empty response from clamd"
            ):
                await _scan_upload_with_clamd(mock_upload, size_limit=1000)


@pytest.mark.anyio
async def test_scan_upload_with_clamd_response_errors():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        mock_upload = AsyncMock(spec=UploadFile)
        mock_upload.seek = AsyncMock()

        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            # 1. FOUND status
            mock_upload.read.side_effect = [b"chunk", b""]
            mock_reader.read.return_value = b"stream: Eicar-Test-Signature FOUND\0"
            res = await _scan_upload_with_clamd(mock_upload, size_limit=1000)
            assert res.signature == "Eicar-Test-Signature"

            # 2. FOUND status with unknown signature name (no spaces before FOUND)
            mock_upload.read.side_effect = [b"chunk", b""]
            mock_reader.read.return_value = b"stream:FOUND\0"
            res = await _scan_upload_with_clamd(mock_upload, size_limit=1000)
            assert res.signature == "unknown"

            # 3. clamd error response format
            mock_upload.read.side_effect = [b"chunk", b""]
            mock_reader.read.return_value = b"stream: SOME_ERROR\0"
            with pytest.raises(
                FileScannerUnavailableError, match="clamd error: stream: SOME_ERROR"
            ):
                await _scan_upload_with_clamd(mock_upload, size_limit=1000)


@pytest.mark.anyio
async def test_check_file_scanner_health_unsupported():
    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "unsupported"
        with pytest.raises(
            FileScannerUnavailableError, match="unsupported scanner backend"
        ):
            await check_file_scanner_health()
