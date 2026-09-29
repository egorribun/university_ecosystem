"""Forward-copy and durable-cleanup contracts of the chat attachment service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.dtos.chat import AttachmentDTO
from app.services.chat import attachment_service
from app.services.chat.attachment_service import (
    AttachmentCleanupError,
    AttachmentCopyError,
    ChatAttachmentService,
)
from app.services.storage import StaticFSStorage

MAX = 1024


def _attachment(url: str = "/static/chat/a.png", size: int = 3) -> AttachmentDTO:
    return AttachmentDTO(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        url=url,
        file_type="image",
        filename="photo.png",
        size=size,
        created_at=datetime(2026, 9, 27, tzinfo=UTC),
    )


@pytest.fixture
def static_backend(tmp_path: Path):
    backend = StaticFSStorage(tmp_path, base_url="/static")
    with (
        patch.object(
            attachment_service.file_utils, "_get_storage_backend", return_value=backend
        ),
        patch.object(
            attachment_service.settings, "chat_attachment_max_size_bytes", MAX
        ),
    ):
        yield backend, tmp_path


def _store(root: Path, name: str, data: bytes) -> None:
    target = root / "chat" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


# ---------------------------------------------------------------------------
# copy_for_forward
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, MAX], ids=["empty", "at-limit"])
async def test_copies_attachments_at_the_size_boundaries(
    static_backend, size: int
) -> None:
    _, root = static_backend
    _store(root, "a.png", b"x" * size)
    service = ChatAttachmentService()
    chat_id = uuid.uuid4()
    seen: dict[str, object] = {}

    async def process_upload(upload, chat, *, locale):
        seen.update(
            size=upload.size, filename=upload.filename, body=await upload.read()
        )
        seen.update(chat=chat, locale=locale)
        return {"url": "/static/chat/copy.png"}

    with patch.object(service, "process_upload", side_effect=process_upload):
        result = await service.copy_for_forward(
            _attachment(size=size), chat_id, locale="ru"
        )

    assert result == {"url": "/static/chat/copy.png"}
    assert seen == {
        "size": size,
        "filename": "photo.png",
        "body": b"x" * size,
        "chat": chat_id,
        "locale": "ru",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected"), [("ru", "ru"), (None, "en")], ids=["explicit", "default"]
)
@pytest.mark.parametrize("size", [-1, MAX + 1], ids=["negative", "over-limit"])
async def test_rejects_invalid_declared_sizes_in_the_callers_locale(
    static_backend, size: int, locale: str | None, expected: str
) -> None:
    rejection = HTTPException(status_code=413)

    with (
        patch.object(
            attachment_service, "raise_http_error", side_effect=rejection
        ) as raise_error,
        pytest.raises(HTTPException),
    ):
        await ChatAttachmentService().copy_for_forward(
            _attachment(size=size), uuid.uuid4(), locale=locale
        )

    raise_error.assert_called_once_with(413, "errors.files.too_large", expected)


@pytest.mark.asyncio
async def test_rejects_a_url_the_storage_backend_does_not_manage(
    static_backend,
) -> None:
    backend, _ = static_backend
    with (
        patch.object(backend, "read_file", new_callable=AsyncMock) as read_file,
        pytest.raises(AttachmentCopyError) as error,
    ):
        await ChatAttachmentService().copy_for_forward(
            _attachment(url="https://evil.example/a.png"), uuid.uuid4(), locale="en"
        )

    assert str(error.value) == "Attachment copy failed"
    read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [b"xx", b"xxxx"], ids=["shorter", "longer"])
async def test_rejects_stored_bytes_that_disagree_with_the_declared_size(
    static_backend, stored: bytes
) -> None:
    _, root = static_backend
    _store(root, "a.png", stored)

    with pytest.raises(AttachmentCopyError) as error:
        await ChatAttachmentService().copy_for_forward(
            _attachment(size=3), uuid.uuid4(), locale="en"
        )

    assert str(error.value) == "Attachment copy failed"


@pytest.mark.asyncio
async def test_hides_storage_read_failures_behind_a_fixed_message(
    static_backend,
) -> None:
    with pytest.raises(AttachmentCopyError) as error:
        await ChatAttachmentService().copy_for_forward(
            _attachment(), uuid.uuid4(), locale="en"
        )

    assert str(error.value) == "Attachment copy failed"
    assert error.value.__cause__ is None


# ---------------------------------------------------------------------------
# durable cleanup_files
# ---------------------------------------------------------------------------


def _backend(*, deletes=None, exists=None) -> MagicMock:
    backend = MagicMock()
    backend.delete_file = AsyncMock(side_effect=deletes)
    backend.exists = AsyncMock(side_effect=exists)
    return backend


async def _durable_cleanup(backend: MagicMock, urls: list[str]) -> None:
    with (
        patch.object(
            attachment_service.file_utils, "_get_storage_backend", return_value=backend
        ),
        patch.object(attachment_service, "_is_managed_url", return_value=True),
    ):
        await ChatAttachmentService().cleanup_files(urls, durable=True)


@pytest.mark.asyncio
async def test_durable_cleanup_succeeds_when_every_object_is_gone() -> None:
    backend = _backend(exists=lambda url: False)

    await _durable_cleanup(backend, [f"/static/chat/{i}" for i in range(10)])

    assert backend.delete_file.await_count == 10


@pytest.mark.asyncio
async def test_durable_cleanup_reports_a_failure_from_an_earlier_batch() -> None:
    urls = [f"/static/chat/{i}" for i in range(10)]
    backend = _backend(exists=lambda url: url == urls[0])

    with pytest.raises(AttachmentCleanupError) as error:
        await _durable_cleanup(backend, urls)

    # The second batch still ran: cleanup stays best-effort until the end.
    assert backend.delete_file.await_count == 10
    assert str(error.value) == "Attachment cleanup failed"


@pytest.mark.asyncio
async def test_durable_cleanup_rejects_an_unmanaged_url_with_a_fixed_message() -> None:
    backend = _backend()
    with (
        patch.object(
            attachment_service.file_utils, "_get_storage_backend", return_value=backend
        ),
        patch.object(attachment_service, "_is_managed_url", return_value=False),
        pytest.raises(AttachmentCleanupError) as error,
    ):
        await ChatAttachmentService().cleanup_files(["https://evil/x"], durable=True)

    assert str(error.value) == "Attachment cleanup failed"
    backend.delete_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_cleanup_uses_the_real_managed_url_check(tmp_path: Path) -> None:
    backend = StaticFSStorage(tmp_path, base_url="https://cdn.example.test/static")
    url = await backend.save_file("chat_uploads/file.pdf", b"data")
    foreign = "https://other.example.test/static/chat_uploads/file.pdf"

    with patch.object(
        attachment_service.file_utils, "_get_storage_backend", return_value=backend
    ):
        await ChatAttachmentService().cleanup_files([url], durable=True)
        assert not await backend.exists(url)

        with (
            patch.object(backend, "delete_file", new=AsyncMock()) as delete,
            pytest.raises(AttachmentCleanupError) as error,
        ):
            await ChatAttachmentService().cleanup_files([foreign], durable=True)

    assert str(error.value) == "Attachment cleanup failed"
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_cleanup_confirms_absence_after_an_ambiguous_delete_error() -> (
    None
):
    gone = _backend(deletes=OSError("reset"), exists=lambda url: False)
    await _durable_cleanup(gone, ["/static/chat/a"])

    still_there = _backend(deletes=OSError("reset"), exists=lambda url: True)
    with pytest.raises(AttachmentCleanupError) as error:
        await _durable_cleanup(still_there, ["/static/chat/a"])

    assert str(error.value) == "Attachment cleanup failed"
