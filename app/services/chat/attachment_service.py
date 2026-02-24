from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import UploadFile
    from app.schemas.dtos.chat import ChatDTO

from app.api.validation import raise_http_error
from app.core.config import settings
from app.utils.files import delete_static_file, save_attachment


class ChatAttachmentService:
    """Handles file uploads and cleanups for the chat service. (TD-1)"""

    async def cleanup_files(self, urls: list[str]) -> None:
        """Delete files from static storage."""
        tasks = [delete_static_file(url) for url in urls if url]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
    ) -> dict[str, object]:
        """Save a single attachment and return its metadata."""
        meta = await save_attachment(
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
