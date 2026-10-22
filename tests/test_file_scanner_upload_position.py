"""A clean upload scan must preserve the bytes for the storage stage."""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.services import file_scanner
from app.services.chat import attachment_service as chat_attachments
from app.services.chat.attachment_service import ChatAttachmentService
from app.utils import files


@pytest.mark.asyncio
async def test_clean_clamd_scan_rewinds_upload_for_the_storage_stage(
    monkeypatch,
) -> None:
    payload = b"%PDF-1.7\nclean upload bytes"
    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(payload),
        size=len(payload),
    )
    settings = file_scanner.settings
    monkeypatch.setattr(settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(settings, "event_file_scanner_backend", "clamd")
    monkeypatch.setattr(settings, "event_file_scanner_socket", "")
    monkeypatch.setattr(settings, "event_file_scanner_host", "127.0.0.1")
    monkeypatch.setattr(settings, "event_file_scanner_port", 3310)
    monkeypatch.setattr(settings, "event_file_scanner_timeout", 5.0)
    monkeypatch.setattr(settings, "event_file_scanner_max_size_mb", 5.0)
    monkeypatch.setattr(settings, "event_file_scanner_max_duration_sec", 30.0)
    monkeypatch.setattr(settings, "environment", "testing")

    reader = AsyncMock()
    reader.read.return_value = b"stream: OK\0"
    writer = MagicMock()
    scan_writes: list[bytes] = []
    writer.write = MagicMock(side_effect=scan_writes.append)
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    async def open_connection(*_args: object, **_kwargs: object):
        return reader, writer

    class RecordingStorage:
        def __init__(self) -> None:
            self.saved: list[tuple[str, bytes, str | None, str | None]] = []

        async def save_file(
            self,
            relative_path: str,
            data: bytes,
            *,
            content_type: str | None = None,
            cache_control: str | None = None,
        ) -> str:
            self.saved.append((relative_path, data, content_type, cache_control))
            return f"/static/{relative_path}"

    storage = RecordingStorage()
    storage_scan = AsyncMock(
        return_value=file_scanner._ScanResult(
            signature=None, duration=0.0, bytes_scanned=len(payload)
        )
    )
    monkeypatch.setattr(file_scanner.asyncio, "open_connection", open_connection)
    monkeypatch.setattr(file_scanner, "_scan_bytes_with_clamd", storage_scan)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: storage)
    await file_scanner._clamav_circuit_breaker.reset()
    try:
        await file_scanner.scan_for_malware(upload, size_bytes=len(payload))

        # This is the event/chat upload storage stage following the explicit
        # pre-scan. It must read and persist exactly the bytes ClamAV saw.
        await files.save_attachment(
            upload,
            "event_files",
            "event_123",
            allowed_mime_types={"application/pdf"},
            allowed_extensions={"pdf"},
            max_size_bytes=1024,
        )
        wire_payload = b"".join(scan_writes)
        stream_header = b"zINSTREAM\0"
        assert wire_payload.startswith(stream_header)
        offset = len(stream_header)
        scanned_chunks = bytearray()
        while True:
            chunk_size = int.from_bytes(wire_payload[offset : offset + 4], "big")
            offset += 4
            if chunk_size == 0:
                break
            scanned_chunks.extend(wire_payload[offset : offset + chunk_size])
            offset += chunk_size
        assert offset == len(wire_payload)
        assert bytes(scanned_chunks) == payload
        assert storage_scan.await_args is not None
        storage_scan_payload = storage_scan.await_args.args[0]
        assert storage_scan_payload == payload
        assert len(storage.saved) == 1
        relative_path, stored_payload, content_type, cache_control = storage.saved[0]
        assert relative_path.startswith("event_files/event_123_")
        assert stored_payload == storage_scan_payload
        assert content_type == "application/pdf"
        assert cache_control == "private, no-store"
    finally:
        await upload.close()
        await file_scanner._clamav_circuit_breaker.reset()


@pytest.mark.asyncio
async def test_unrecognized_clamd_status_fails_closed_before_upload(
    monkeypatch,
) -> None:
    payload = b"synthetic document for scanner contract"
    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(payload),
        size=len(payload),
    )
    settings = file_scanner.settings
    monkeypatch.setattr(settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(settings, "event_file_scanner_backend", "clamd")
    monkeypatch.setattr(settings, "event_file_scanner_socket", "")
    monkeypatch.setattr(settings, "event_file_scanner_host", "127.0.0.1")
    monkeypatch.setattr(settings, "event_file_scanner_port", 3310)
    monkeypatch.setattr(settings, "event_file_scanner_timeout", 5.0)
    monkeypatch.setattr(settings, "event_file_scanner_max_size_mb", 5.0)
    monkeypatch.setattr(settings, "event_file_scanner_max_duration_sec", 30.0)
    monkeypatch.setattr(settings, "environment", "testing")

    reader = AsyncMock()
    reader.read.return_value = b"stream: NOT OK\0"
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    async def open_connection(*_args: object, **_kwargs: object):
        return reader, writer

    monkeypatch.setattr(file_scanner.asyncio, "open_connection", open_connection)
    persist_upload = AsyncMock(return_value={"url": "unused"})
    monkeypatch.setattr(chat_attachments, "save_attachment", persist_upload)
    await file_scanner._clamav_circuit_breaker.reset()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await ChatAttachmentService().process_upload(
                upload, uuid.uuid4(), locale="en"
            )

        assert exc_info.value.status_code == 503
        persist_upload.assert_not_awaited()
    finally:
        await upload.close()
        await file_scanner._clamav_circuit_breaker.reset()
