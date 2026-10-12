"""Ownership checks for destructive operations on uploaded content media."""

from __future__ import annotations

import re
import uuid

from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend, normalize_filename_prefix


def _owned_event_image_backend(
    file_url: str, event_id: uuid.UUID | int
) -> StaticFSStorage | S3Storage | None:
    """Return the storage backend only for a canonical event-owned image key."""
    if not isinstance(event_id, uuid.UUID):
        return None

    backend = _get_storage_backend()
    key: str | None = None
    selected_backend: StaticFSStorage | S3Storage
    if isinstance(backend, StaticFSStorage):
        selected_backend = backend
        relative_path = backend._extract_relative_path(file_url)
        if relative_path is None:
            return None
        key = relative_path.as_posix()
    elif isinstance(backend, S3Storage):
        selected_backend = backend
        key = backend._extract_key(file_url)
        if key is None:
            return None
    else:
        return None

    parts = key.split("/")
    if len(parts) != 3 or parts[:2] != ["tmp", "event_images"]:
        return None

    owner_prefix = normalize_filename_prefix(f"event_{event_id}")
    filename_pattern = rf"{re.escape(owner_prefix)}_[0-9a-f]{{32}}\.(?:jpg|png|webp)"
    if re.fullmatch(filename_pattern, parts[2], flags=re.ASCII) is None:
        return None

    return selected_backend


async def delete_owned_event_image(file_url: str, *, event_id: uuid.UUID | int) -> bool:
    """Delete only an image key generated for this event; reject legacy URLs."""
    backend = _owned_event_image_backend(file_url, event_id)
    if backend is None:
        return False

    await backend.delete_file(file_url)
    return True
