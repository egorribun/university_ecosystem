"""Forwarded uploads remain owned by the attachment service on every outcome."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.schemas.dtos.chat import AttachmentDTO
from app.services.chat import attachment_service
from app.services.storage import StaticFSStorage


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "error", "cancellation"])
async def test_forward_copy_closes_its_upload_without_replacing_the_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
) -> None:
    payload = b"forwarded attachment bytes"
    backend = StaticFSStorage(tmp_path, base_url="/static")
    source_url = await backend.save_file("chat/source.bin", payload)
    attachment = AttachmentDTO(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        url=source_url,
        file_type="file",
        filename="source.bin",
        size=len(payload),
        created_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    chat_id = uuid.uuid4()
    uploaded: list[UploadFile] = []
    expected_result = {"url": "/static/chat/destination.bin", "size": len(payload)}
    failure = (
        asyncio.CancelledError("upload cancelled")
        if outcome == "cancellation"
        else OSError("upload failed")
    )
    service = attachment_service.ChatAttachmentService()

    async def process_upload(
        upload: UploadFile, destination: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]:
        uploaded.append(upload)
        assert not upload.file.closed
        assert await upload.read() == payload
        assert upload.filename == attachment.filename
        assert upload.size == len(payload)
        assert destination == chat_id
        assert locale == "ru"
        if outcome != "success":
            raise failure
        return expected_result

    monkeypatch.setattr(
        attachment_service.file_utils, "_get_storage_backend", lambda: backend
    )
    monkeypatch.setattr(service, "process_upload", process_upload)

    try:
        if outcome == "success":
            result = await service.copy_for_forward(attachment, chat_id, locale="ru")
            assert result is expected_result
        else:
            with pytest.raises(type(failure)) as raised:
                await service.copy_for_forward(attachment, chat_id, locale="ru")
            assert raised.value is failure

        assert len(uploaded) == 1
        assert uploaded[0].file.closed
    finally:
        # Negative controls must not leave their intentionally leaked test file open.
        for upload in uploaded:
            await upload.close()
