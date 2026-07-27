"""Closure tests for chat attachment metadata processing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.chat.attachment_service import ChatAttachmentService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("detected_type", "expected_file_type"),
    [("image/png", "image"), ("video/mp4", "video"), ("application/pdf", "file")],
)
async def test_process_upload_maps_detected_file_types(
    detected_type, expected_file_type
):
    upload = SimpleNamespace(size=12, filename="original.bin")
    meta = {
        "url": "/static/chat/file",
        "detected_type": detected_type,
        "filename": "stored.bin",
        "size": "12",
    }

    with (
        patch(
            "app.services.chat.attachment_service.scan_for_malware",
            new=AsyncMock(),
        ) as scan,
        patch(
            "app.services.chat.attachment_service.save_attachment",
            new=AsyncMock(return_value=meta),
        ) as save,
    ):
        result = await ChatAttachmentService().process_upload(
            upload, uuid4(), locale="en"
        )

    scan.assert_awaited_once_with(upload, locale="en", size_bytes=12)
    save.assert_awaited_once()
    assert result == {
        "url": "/static/chat/file",
        "file_type": expected_file_type,
        "filename": "stored.bin",
        "size": 12,
    }


@pytest.mark.asyncio
async def test_process_upload_uses_content_type_and_filename_fallbacks():
    upload = SimpleNamespace(size=None, filename="upload.txt")
    meta = {"content_type": "text/plain", "size": None}

    with (
        patch("app.services.chat.attachment_service.scan_for_malware", new=AsyncMock()),
        patch(
            "app.services.chat.attachment_service.save_attachment",
            new=AsyncMock(return_value=meta),
        ),
    ):
        result = await ChatAttachmentService().process_upload(
            upload, uuid4(), locale=None
        )

    assert result["filename"] == "upload.txt"
    assert result["url"] == ""
    assert result["size"] == 0


@pytest.mark.asyncio
async def test_process_upload_rejects_missing_metadata():
    upload = SimpleNamespace(size=1, filename="file.bin")

    with (
        patch("app.services.chat.attachment_service.scan_for_malware", new=AsyncMock()),
        patch(
            "app.services.chat.attachment_service.save_attachment",
            new=AsyncMock(return_value="/static/file"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ChatAttachmentService().process_upload(upload, uuid4(), locale="en")

    assert exc_info.value.status_code == 500
