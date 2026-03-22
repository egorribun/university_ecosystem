import io

import pytest

from app.services.file_scanner import (
    FileScannerPayloadTooLarge,
    _scanner_duration_limit_seconds,
    _scanner_size_limit_bytes,
    _UploadStream,
)


def test_scanner_config_helpers(monkeypatch):
    import app.services.file_scanner as fs

    # Test valid MB conversion
    monkeypatch.setattr(fs.settings, "event_file_scanner_max_size_mb", 10.0)
    # 10MB = 10 * 1024 * 1024 = 10485760
    assert _scanner_size_limit_bytes() == 10485760

    monkeypatch.setattr(fs.settings, "event_file_scanner_max_duration_sec", 15.5)
    assert _scanner_duration_limit_seconds() == 15.5


def test_upload_stream_enforcement():
    raw = io.BytesIO(b"abcdefgh")
    # Limit at 4 bytes
    stream = _UploadStream(raw, limit=4, chunk_size=2)

    # First chunk (2 bytes)
    chunk1 = stream.read(2)
    assert chunk1 == b"ab"
    assert stream.bytes_scanned == 2

    # Second chunk (next 2 bytes are safe)
    chunk2 = stream.read(2)
    assert chunk2 == b"cd"
    assert stream.bytes_scanned == 4

    # Third chunk exceeds
    with pytest.raises(FileScannerPayloadTooLarge) as exc:
        stream.read(1)
    assert exc.value.size_bytes == 5
    assert exc.value.limit_bytes == 4


def test_upload_stream_no_limit():
    raw = io.BytesIO(b"abcde")
    stream = _UploadStream(raw, limit=0)
    data = stream.read(10)
    assert data == b"abcde"
    assert stream.bytes_scanned == 5


def test_upload_stream_delegation():
    raw = io.BytesIO(b"abcde")
    stream = _UploadStream(raw, limit=10)
    assert stream.tell() == 0
    stream.read(2)
    assert stream.tell() == 2
    stream.seek(0)
    assert stream.tell() == 0
    stream.close()
    assert raw.closed


def test_scan_with_clamd_stream_ok(monkeypatch):
    from unittest.mock import MagicMock

    import app.services.file_scanner as fs

    mock_client = MagicMock()
    mock_client.instream.return_value = {"stream": ("OK",)}
    monkeypatch.setattr(fs, "_create_clamd_client", lambda: mock_client)

    stream = io.BytesIO(b"clean")
    assert fs._scan_with_clamd_stream(stream) is None
    mock_client.instream.assert_called_once_with(stream)


def test_scan_with_clamd_stream_found(monkeypatch):
    from unittest.mock import MagicMock

    import app.services.file_scanner as fs

    mock_client = MagicMock()
    mock_client.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}
    monkeypatch.setattr(fs, "_create_clamd_client", lambda: mock_client)

    assert fs._scan_with_clamd_stream(io.BytesIO(b"infected")) == "Eicar-Test-Signature"


def test_scan_with_clamd_stream_error(monkeypatch):
    from unittest.mock import MagicMock

    import app.services.file_scanner as fs

    mock_client = MagicMock()
    mock_client.instream.return_value = {"stream": ("ERROR", "Internal fault")}
    monkeypatch.setattr(fs, "_create_clamd_client", lambda: mock_client)

    from app.services.file_scanner import FileScannerUnavailableError

    with pytest.raises(FileScannerUnavailableError) as exc:
        fs._scan_with_clamd_stream(io.BytesIO(b"data"))
    assert "Internal fault" in str(exc.value)
