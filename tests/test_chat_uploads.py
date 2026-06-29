import io

import pytest
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.localization import translate
from app.models.chat import Attachment, Chat
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatMessageDispatcher
from app.services.chat.notification_service import ChatNotificationService
from app.utils import files


def _fallback_detect_mime(data: bytes) -> str | None:
    """Simple MIME detection fallback for platforms without libmagic."""
    if not data:
        return None
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"RIFF") and b"WEBP" in data[:12]:
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    # SVG detection
    if b"<svg" in data[:1024].lower():
        return "image/svg+xml"
    # Assume text/plain for printable ASCII
    try:
        data[:512].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


@pytest.fixture(autouse=True)
def _mock_mime_detection(monkeypatch):
    """Mock MIME detection for platforms without libmagic (e.g., Windows)."""
    monkeypatch.setattr(files, "detect_mime_type", _fallback_detect_mime)


class _RecordingStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def save_file(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        self.calls.append(
            (
                "save",
                (relative_path, data),
                {"content_type": content_type, "cache_control": cache_control},
            )
        )
        return f"https://cdn.example/{relative_path}"

    async def delete_file(self, file_url: str) -> None:
        self.calls.append(("delete", (file_url,), {}))


@pytest.mark.asyncio
async def test_send_message_blocks_infected_file(
    tmp_path, monkeypatch, db_session, user_factory
):
    sender = await user_factory()
    recipient = await user_factory()
    chat = Chat()
    chat.participants.extend([sender, recipient])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    payload = b"suspicious payload"
    upload = UploadFile(
        filename="exploit.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "chat_attachment_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "chat_attachment_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "chat_attachment_max_size_bytes", 1024)

    async def infected_scan(*_args, **_kwargs):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=translate("errors.files.infected", locale="en"),
        )

    monkeypatch.setattr(files, "scan_for_malware", infected_scan)
    monkeypatch.setattr(
        ChatNotificationService,
        "notify_new_message",
        lambda *_, **__: None,
    )

    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db_session)
    attachments = ChatAttachmentService()
    notifications = ChatNotificationService(db_session)
    service = ChatMessageDispatcher(uow, attachments, notifications)

    with pytest.raises((HTTPException, ExceptionGroup)) as excinfo:
        await service.send_message(
            chat.id,
            user=sender,
            content="Hello",
            files=[upload],
            locale="en",
        )

    # asyncio.TaskGroup wraps exceptions in ExceptionGroup
    if isinstance(excinfo.value, ExceptionGroup):
        http_exceptions = [
            e for e in excinfo.value.exceptions if isinstance(e, HTTPException)
        ]
        assert http_exceptions, "Expected HTTPException inside ExceptionGroup"
        assert http_exceptions[0].status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        assert excinfo.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    upload_dir = tmp_path / "chat_uploads"
    assert not upload_dir.exists() or not any(upload_dir.iterdir())


@pytest.mark.asyncio
async def test_send_message_generates_public_urls(
    monkeypatch, db_session, user_factory
):
    sender = await user_factory()
    recipient = await user_factory()
    chat = Chat()
    chat.participants.extend([sender, recipient])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    upload = UploadFile(
        filename="note.txt",
        file=io.BytesIO(b"hello"),
        headers=Headers({"content-type": "text/plain"}),
    )

    backend = _RecordingStorage()

    monkeypatch.setattr(settings, "chat_attachment_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "chat_attachment_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "chat_attachment_max_size_bytes", 1024)
    monkeypatch.setattr(files, "storage_backend", backend)
    monkeypatch.setattr(files, "_default_storage_backend", backend)
    monkeypatch.setattr(
        files, "_storage_backend_snapshot", files._storage_backend_signature()
    )

    async def _noop_notify(*_, **__):
        pass

    monkeypatch.setattr(ChatNotificationService, "notify_new_message", _noop_notify)

    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db_session)
    attachments = ChatAttachmentService()
    notifications = ChatNotificationService(db_session)
    service = ChatMessageDispatcher(uow, attachments, notifications)
    message = await service.send_message(
        chat.id,
        user=sender,
        content="Hello",
        files=[upload],
        locale="en",
    )

    # message is now a MessageResponse (Pydantic schema), attachments are included
    assert len(message.attachments) == 1
    attachment = message.attachments[0]

    assert attachment.url.startswith("https://cdn.example/chat_uploads/")
    assert attachment.size == 5

    stored = await db_session.execute(
        select(Attachment).where(Attachment.id == attachment.id)
    )
    assert stored.scalar_one().url == attachment.url

    method, (relative_path, _data), kwargs = backend.calls[0]
    assert method == "save"
    assert relative_path.startswith("chat_uploads/")
    assert kwargs["content_type"] == "text/plain"
