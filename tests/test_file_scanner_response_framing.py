"""ClamAV replies must be complete independently of transport chunking."""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile

from app.services import file_scanner as scanner


def connection(monkeypatch, chunks, *, timeout=1):
    reader = SimpleNamespace(read=AsyncMock(side_effect=chunks))
    writer = SimpleNamespace(
        write=Mock(), drain=AsyncMock(), close=Mock(), wait_closed=AsyncMock()
    )
    monkeypatch.setattr(
        scanner,
        "settings",
        SimpleNamespace(
            event_file_scanner_timeout=timeout,
            event_file_scanner_socket="",
            event_file_scanner_host="localhost",
            event_file_scanner_port=3310,
        ),
    )
    monkeypatch.setattr(
        asyncio, "open_connection", AsyncMock(return_value=(reader, writer))
    )
    return reader, writer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "signature"),
    [
        ([b"stream: O", b"K", b"\0"], None),
        ([b"stream: OK", b"virus FOUND\0"], "OKvirus"),
        (
            [b"s", b"tream: EICAR-Test-", b"Signature FOUND", b"\0"],
            "EICAR-Test-Signature",
        ),
        ([b"stream:", b"FOUND", b"\0"], "unknown"),
    ],
)
async def test_upload_scan_reads_complete_fragmented_reply(
    monkeypatch, chunks, signature
):
    reader, writer = connection(monkeypatch, chunks)
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="sample.bin")
    try:
        result = await scanner._scan_upload_with_clamd(upload, size_limit=100)
        assert result.signature == signature
        assert result.bytes_scanned == 7
        assert reader.read.await_count == len(chunks)
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()
    finally:
        await upload.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        [b""],
        [b"stream: OK", b""],
        [b"stream: OK\0junk"],
        [b"stream: OK\0\0"],
        [b"x" * 4096],
    ],
)
async def test_upload_scan_rejects_incomplete_or_invalid_frames(monkeypatch, chunks):
    _, writer = connection(monkeypatch, chunks)
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="sample.bin")
    try:
        with pytest.raises(scanner.FileScannerUnavailableError):
            await scanner._scan_upload_with_clamd(upload, size_limit=100)
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()
    finally:
        await upload.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [4095, 4096, 4097])
async def test_response_frame_exact_size_boundary(length):
    reader = asyncio.StreamReader()
    response = b"x" * (length - 1) + b"\0"
    reader.feed_data(response)
    reader.feed_eof()
    if length <= 4096:
        assert await scanner._read_clamd_response(reader) == response
    else:
        with pytest.raises(scanner.FileScannerUnavailableError):
            await scanner._read_clamd_response(reader)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_unterminated_reply_is_bounded_and_closes_connection(
    monkeypatch, cancel
):
    waiting = asyncio.Event()

    async def stalled_read(size):
        waiting.set()
        await asyncio.Event().wait()

    _, writer = connection(
        monkeypatch, stalled_read, timeout=1 if cancel else 0.02
    )
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="sample.bin")
    task = asyncio.create_task(
        scanner._scan_upload_with_clamd(upload, size_limit=100)
    )
    try:
        await asyncio.wait_for(waiting.wait(), timeout=1)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(
                scanner.FileScannerUnavailableError, match="timed out"
            ):
                await asyncio.wait_for(task, timeout=1)
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await upload.close()
