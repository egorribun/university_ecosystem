import asyncio
import mimetypes
import re
import secrets
from pathlib import Path
from typing import Final

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_IMAGE_TYPES: Final[set[str]] = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE: Final[int] = 5 * 1024 * 1024

_PREFIX_CLEAN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PREFERRED_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="file too large",
        )
    return data


def _ext_from_mime(mime: str) -> str:
    exts = mimetypes.guess_all_extensions(mime) or []
    return exts[0] if exts else ""


def _detect_image_mime(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_filename_prefix(prefix: str) -> str:
    """Return a safe, lowercase slug suitable for file names."""

    raw = prefix.strip()
    cleaned = _PREFIX_CLEAN_RE.sub("-", raw)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-_.")
    return cleaned or "file"


def _gen_name(prefix: str, ext: str) -> str:
    safe_prefix = normalize_filename_prefix(prefix)
    token = secrets.token_hex(16)
    ext = ext if ext.startswith(".") else f".{ext}" if ext else ""
    return f"{safe_prefix}_{token}{ext}"


async def save_image(upload: UploadFile, subdir: str, prefix: str) -> str:
    declared_type = (upload.content_type or "").lower()
    if declared_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="unsupported media type",
        )
    data = await _read_limited(upload, MAX_IMAGE_SIZE)
    detected_type = _detect_image_mime(data)
    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="unsupported media type",
        )
    if detected_type != declared_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="content type mismatch",
        )
    ext = _PREFERRED_EXTENSIONS.get(detected_type) or _ext_from_mime(detected_type)
    name = _gen_name(prefix, ext)
    base = settings.static_dir_path
    sanitized_subdir = subdir.strip("/ ")
    target_dir = base / sanitized_subdir
    await asyncio.to_thread(_ensure_dir, target_dir)
    path = target_dir / name
    await asyncio.to_thread(path.write_bytes, data)
    # Return canonical public URL without accidental duplicate slashes.
    return f"/static/{sanitized_subdir}/{name}"
