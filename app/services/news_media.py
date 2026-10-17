"""Canonical storage-key validation for newly uploaded news images."""

from __future__ import annotations

import re

from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend

_NEWS_IMAGE_KEY = re.compile(
    r"news_images/news_[0-9a-f]{32}\.(?:jpg|png|webp)", flags=re.ASCII
)


def canonical_news_image_key(file_url: str) -> str | None:
    """Return a key only when *file_url* is the canonical generated news key."""
    if not isinstance(file_url, str) or not file_url:
        return None

    backend = _get_storage_backend()
    if isinstance(backend, StaticFSStorage):
        relative_path = backend._extract_relative_path(file_url)
        if relative_path is None:
            return None
        key = relative_path.as_posix()
        canonical_url = (
            f"{backend.base_url.rstrip('/')}/{key}" if backend.base_url else f"/{key}"
        )
    elif isinstance(backend, S3Storage):
        extracted_key = backend._extract_key(file_url)
        if extracted_key is None:
            return None
        key = extracted_key
        canonical_url = f"{backend.base_url.rstrip('/')}/{key}"
    else:
        return None

    if file_url != canonical_url or _NEWS_IMAGE_KEY.fullmatch(key) is None:
        return None
    return key
