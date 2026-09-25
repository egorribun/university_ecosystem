"""Chat attachment service — file uploads, malware scanning, and cleanups.

This module owns the file-side of the chat lifecycle. It is intentionally
narrow: callers hand it a single ``UploadFile`` plus the chat ID, and
``process_upload`` returns the persisted metadata (URL, size, file type)
that the message-creation path consumes. Malware scanning runs *before*
storage to keep tainted bytes off disk.

The two helper methods (``cleanup_files`` / ``collect_urls``) support chat
deletion: collecting URLs across all messages, then deleting their objects.
Outbox cleanup is durable; inline upload rollback remains best-effort.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import TYPE_CHECKING  # TD-23-04 (audit 2026-03-25 Wave 23)

if TYPE_CHECKING:
    from fastapi import UploadFile

    from app.schemas.dtos.chat import AttachmentDTO, ChatDTO

from app.api.validation import raise_http_error
from app.core.config import settings
from app.services.file_scanner import scan_for_malware
from app.services.storage import S3Storage, StaticFSStorage, StorageBackend
from app.utils import files as file_utils
from app.utils.files import delete_static_file, save_attachment


class AttachmentCleanupError(RuntimeError):
    """A stored attachment could not be verified as deleted."""


class AttachmentCopyError(RuntimeError):
    """A forwarded attachment could not be copied safely."""


def _is_managed_url(backend: StorageBackend, url: str) -> bool:
    """Reject URLs a backend would silently ignore or reinterpret as another key."""
    if isinstance(backend, S3Storage):
        return backend._extract_key(url) is not None
    if isinstance(backend, StaticFSStorage):
        relative = backend._extract_relative_path(url)
        return (
            relative is not None and url == f"{backend.base_url}/{relative.as_posix()}"
        )
    return True


class ChatAttachmentService:
    """Handles file uploads and cleanups for the chat service. (TD-1)"""

    async def cleanup_files(self, urls: list[str], *, durable: bool = False) -> None:
        """Delete files, requiring verified absence for outbox delivery.

        Failed upload rollback must not replace its original exception, hence
        best-effort is the default. Durable outbox cleanup surfaces any failed
        object and lets the worker retry the *entire* idempotent batch.
        """
        nonempty_urls = [url for url in urls if url]
        if not nonempty_urls:
            return

        delete_one: Callable[[str], Awaitable[None]]
        if durable:
            backend = file_utils._get_storage_backend()

            async def delete_verified(url: str) -> None:
                if not _is_managed_url(backend, url):
                    raise AttachmentCleanupError("Attachment cleanup failed")
                try:
                    await backend.delete_file(url)
                except Exception:
                    # A concurrent replay may have removed the object while
                    # this delete returned an ambiguous storage error. Only
                    # the verified absent postcondition can acknowledge it;
                    # the outer batch converts any probe failure to a safe NAK.
                    if not await backend.exists(url):
                        return
                    raise AttachmentCleanupError("Attachment cleanup failed") from None
                if await backend.exists(url):
                    raise AttachmentCleanupError("Attachment cleanup failed")

            delete_one = delete_verified
        else:
            delete_one = delete_static_file

        failed = False
        # Each S3 delete/HEAD creates an async client. A legacy bulk history
        # clear can contain thousands of URLs, so bound both task allocation
        # and open connections without losing best-effort progress in a batch.
        for offset in range(0, len(nonempty_urls), 8):
            outcomes = await asyncio.gather(
                *(delete_one(url) for url in nonempty_urls[offset : offset + 8]),
                return_exceptions=True,
            )
            if durable:
                for outcome in outcomes:
                    if isinstance(outcome, asyncio.CancelledError):
                        raise outcome
                    if isinstance(outcome, BaseException):
                        failed = True
        if failed:
            raise AttachmentCleanupError("Attachment cleanup failed") from None

    async def copy_for_forward(
        self, attachment: AttachmentDTO, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]:
        """Rescan a source attachment into a separately owned destination object."""
        from fastapi import UploadFile

        max_size = settings.chat_attachment_max_size_bytes
        if attachment.size < 0 or attachment.size > max_size:
            raise_http_error(413, "errors.files.too_large", str(locale or "en"))

        backend = file_utils._get_storage_backend()
        if not _is_managed_url(backend, attachment.url):
            raise AttachmentCopyError("Attachment copy failed")
        try:
            data = await backend.read_file(attachment.url, max_bytes=max_size)
        except Exception:  # RZ-22-01-JUSTIFIED: domain conversion hides storage URL and provider error text
            raise AttachmentCopyError("Attachment copy failed") from None
        if len(data) != attachment.size or len(data) > max_size:
            raise AttachmentCopyError("Attachment copy failed")

        upload = UploadFile(
            file=BytesIO(data), size=len(data), filename=attachment.filename
        )
        try:
            return await self.process_upload(upload, chat_id, locale=locale)
        finally:
            await upload.close()

    async def collect_urls(self, chat: ChatDTO) -> list[str]:
        """Collect all attachment URLs from a chat's messages."""
        urls: list[str] = []
        for message in chat.messages:
            for attachment in message.attachments:
                if attachment.url:
                    urls.append(attachment.url)
        return urls

    async def process_upload(
        self, upload: UploadFile, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]:
        """Save a single attachment and return its metadata."""
        await scan_for_malware(upload, locale=locale, size_bytes=upload.size)
        meta: str | dict[str, object] = await save_attachment(
            upload,
            "chat_uploads",
            f"chat_{chat_id}",
            locale=locale,
            allowed_mime_types=settings.chat_attachment_allowed_mime_types_set,
            allowed_extensions=settings.chat_attachment_allowed_extensions_set,
            max_size_bytes=settings.chat_attachment_max_size_bytes,
            return_meta=True,
        )
        if not isinstance(meta, dict):
            raise_http_error(500, "errors.chat.attachment_failed", str(locale or "en"))

        detected_type = str(meta.get("detected_type") or meta.get("content_type") or "")
        file_type = "file"
        if detected_type.startswith("image/"):
            file_type = "image"
        elif detected_type.startswith("video/"):
            file_type = "video"

        return {
            "url": str(meta.get("url") or ""),
            "file_type": file_type,
            "filename": str(meta.get("filename") or upload.filename or "attachment"),
            "size": int(str(meta.get("size") or 0)),
        }
