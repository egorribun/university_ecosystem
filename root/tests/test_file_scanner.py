"""Unit tests for file scanner functionality."""

import io
from unittest.mock import patch

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
