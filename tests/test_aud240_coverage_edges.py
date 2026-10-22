"""Meaningful edge contracts for AUD240 attachment safety paths."""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.core.config import settings
from app.services.chat import attachment_service
from app.services.chat.attachment_service import (
    AttachmentCopyError,
    ChatAttachmentService,
)
from app.services.storage import S3Storage, StaticFSStorage
from app.utils import files


def _small_jpeg() -> bytes:
    image = Image.new("RGB", (4, 4), color=(27, 84, 139))
    payload = BytesIO()
    image.save(payload, format="JPEG")
    return payload.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "managed"),
    [
        ("https://cdn.example.test/attachments/chat/file.jpg", True),
        ("https://outside.example.test/attachments/chat/file.jpg", False),
    ],
)
async def test_s3_forward_reads_only_backend_managed_urls(
    monkeypatch: pytest.MonkeyPatch, url: str, managed: bool
) -> None:
    backend = S3Storage(
        bucket="attachments",
        base_url="https://cdn.example.test/attachments",
    )
    backend.read_file = AsyncMock(return_value=b"data")
    monkeypatch.setattr(
        attachment_service.file_utils, "_get_storage_backend", lambda: backend
    )
    service = ChatAttachmentService()
    expected = {"url": "s3://stored", "size": 4}
    process = AsyncMock(return_value=expected)
    monkeypatch.setattr(service, "process_upload", process)
    source = SimpleNamespace(url=url, size=4, filename="file.jpg")

    if managed:
        max_size = settings.chat_attachment_max_size_bytes
        result = await service.copy_for_forward(source, uuid4(), locale="en")

        assert result == expected
        backend.read_file.assert_awaited_once_with(url, max_bytes=max_size)
        process.assert_awaited_once()
    else:
        with pytest.raises(AttachmentCopyError, match="Attachment copy failed"):
            await service.copy_for_forward(source, uuid4(), locale="en")

        backend.read_file.assert_not_awaited()
        process.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_attachment_cleanup_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SimpleNamespace(
        delete_file=AsyncMock(side_effect=asyncio.CancelledError()),
        exists=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        attachment_service.file_utils, "_get_storage_backend", lambda: backend
    )

    with pytest.raises(asyncio.CancelledError):
        await ChatAttachmentService().cleanup_files(["owned-object"], durable=True)

    backend.delete_file.assert_awaited_once_with("owned-object")
    backend.exists.assert_not_awaited()


@pytest.mark.parametrize("failure_path", ["detector", "legacy-module"])
def test_mime_detection_falls_back_to_real_image_signature_when_magic_fails(
    monkeypatch: pytest.MonkeyPatch, failure_path: str
) -> None:
    payload = _small_jpeg()
    detector = SimpleNamespace(from_buffer=Mock())
    if failure_path == "detector":
        detector.from_buffer.side_effect = RuntimeError("synthetic libmagic failure")
        monkeypatch.setattr(files, "_magic_mime_detector", detector)
        monkeypatch.setattr(files, "_magic_module", None)
    else:
        detector.from_buffer.side_effect = AttributeError("legacy detector API")
        legacy_magic = SimpleNamespace(
            from_buffer=Mock(side_effect=OSError("synthetic legacy failure"))
        )
        monkeypatch.setattr(files, "_magic_mime_detector", detector)
        monkeypatch.setattr(files, "_magic_module", legacy_magic)

    assert files.detect_mime_type(payload) == "image/jpeg"
    assert payload.startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_chat_image_pixel_budget_scans_original_and_rejects_before_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    original = _small_jpeg()
    backend = StaticFSStorage(tmp_path, base_url="/static")
    scanned_payloads: list[bytes] = []

    async def record_scan(data: bytes, **_kwargs: object) -> None:
        scanned_payloads.append(data)

    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", record_scan)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "image/jpeg")
    monkeypatch.setattr(settings, "chat_attachment_max_size_bytes", 4096)
    monkeypatch.setattr(settings, "image_max_pixels", 15)
    upload = UploadFile(
        filename="image.jpg",
        file=BytesIO(original),
        size=len(original),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    try:
        with pytest.raises(HTTPException) as error:
            await ChatAttachmentService().process_upload(upload, uuid4(), locale="en")
    finally:
        await upload.close()

    assert error.value.status_code == 413
    assert scanned_payloads == [original]
    assert not (tmp_path / "chat_uploads").exists()
