"""Ownership checks for destructive operations on uploaded content media."""

from __future__ import annotations

import os
import re
import uuid

from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend, normalize_filename_prefix

logger = get_logger(__name__)


def _owned_event_image_storage(
    file_url: str, event_id: uuid.UUID | int
) -> tuple[StaticFSStorage | S3Storage, str] | None:
    """Return the backend and parsed key only for a canonical event-owned image."""
    if not isinstance(event_id, uuid.UUID):
        return None

    backend = _get_storage_backend()
    selected_backend: StaticFSStorage | S3Storage
    selected_key: str
    if isinstance(backend, StaticFSStorage):
        selected_backend = backend
        relative_path = backend._extract_relative_path(file_url)
        if relative_path is None:
            return None
        selected_key = relative_path.as_posix()
    elif isinstance(backend, S3Storage):
        selected_backend = backend
        extracted_key = backend._extract_key(file_url)
        if extracted_key is None:
            return None
        selected_key = extracted_key
    else:
        return None

    parts = selected_key.split("/")
    if len(parts) != 3 or parts[:2] != ["tmp", "event_images"]:
        return None

    owner_prefix = normalize_filename_prefix(f"event_{event_id}")
    filename_pattern = rf"{re.escape(owner_prefix)}_[0-9a-f]{{32}}\.(?:jpg|png|webp)"
    if re.fullmatch(filename_pattern, parts[2], flags=re.ASCII) is None:
        return None

    return selected_backend, selected_key


def _owned_event_image_backend(
    file_url: str, event_id: uuid.UUID | int
) -> StaticFSStorage | S3Storage | None:
    """Preserve the backend-only helper for existing internal callers."""
    owned_storage = _owned_event_image_storage(file_url, event_id)
    return owned_storage[0] if owned_storage is not None else None


def _event_image_storage_key(
    backend: StaticFSStorage | S3Storage, file_url: str
) -> str | None:
    """Normalize a URL to its storage key without changing backend semantics."""
    if isinstance(backend, StaticFSStorage):
        relative_path = backend._extract_relative_path(file_url)
        return relative_path.as_posix() if relative_path is not None else None
    return backend._extract_key(file_url)


async def delete_owned_event_image(file_url: str, *, event_id: uuid.UUID | int) -> bool:
    """Delete a canonical owner key after callers establish it is unreferenced."""
    backend = _owned_event_image_backend(file_url, event_id)
    if backend is None:
        return False

    await backend.delete_file(file_url)
    return True


async def delete_unreferenced_owned_event_image(
    file_url: str,
    *,
    event_id: uuid.UUID | int,
    db_session: AsyncDatabaseSession,
) -> bool:
    """Delete a canonical event image only when no event still references it.

    The database check runs after the caller commits its image-URL change. If
    the query cannot establish that the key is unreferenced, retain the object.
    """
    owned_storage = _owned_event_image_storage(file_url, event_id)
    if owned_storage is None:
        return False
    backend, storage_key = owned_storage
    filename = storage_key.rsplit("/", 1)[-1]

    try:
        from sqlalchemy import func, select

        from app.models import Event

        references = await db_session.execute(
            select(Event.image_url).where(
                func.lower(Event.image_url).contains(filename.lower())
            )
        )
        for referenced_url in references.scalars():
            if not isinstance(referenced_url, str):
                return False
            referenced_key = _event_image_storage_key(backend, referenced_url)
            if referenced_key is None:
                return False
            reference_filename = referenced_key.rsplit("/", 1)[-1]
            if isinstance(backend, StaticFSStorage):
                # StaticFS URL parsing is intentionally path-oriented. An absolute
                # alias host can therefore normalize to a different-looking key
                # with the same leaf; retain rather than risk deleting that object.
                reference_filename = reference_filename.split("?", 1)[0].split("#", 1)[
                    0
                ]
                same_key = os.path.normcase(referenced_key) == os.path.normcase(
                    storage_key
                )
                same_filename = os.path.normcase(
                    reference_filename
                ) == os.path.normcase(filename)
            else:
                same_key = referenced_key == storage_key
                same_filename = reference_filename == filename
            if same_key or same_filename:
                return False
    except Exception as exc:  # RZ-22-01-JUSTIFIED: fail closed on uncertainty
        logger.warning(
            "event_image_reference_check_failed",
            error_type=type(exc).__name__,
        )
        return False

    await backend.delete_file(file_url)
    return True
