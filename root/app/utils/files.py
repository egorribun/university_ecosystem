import asyncio
import logging
import mimetypes
import re
import secrets
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.localization import translate
from app.services.file_scanner import scan_for_malware
from app.utils.images import optimize_image

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES: Final[set[str]] = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE: Final[int] = 5 * 1024 * 1024

_PREFIX_CLEAN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PREFERRED_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

try:  # pragma: no cover - exercised indirectly via detect_mime_type
    import magic  # type: ignore[import]
except ImportError:  # pragma: no cover - handled at runtime
    magic = None  # type: ignore[assignment]

_MAGIC_NOT_INITIALIZED: Final[object] = object()
_magic_mime_detector: Any = _MAGIC_NOT_INITIALIZED


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


async def _read_limited(
    upload: UploadFile, limit: int, *, locale: str | None = None
) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=translate("errors.files.too_large", locale=locale),
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


def _normalize_mime_type(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower()
    if ";" in normalized:
        normalized = normalized.split(";", 1)[0].strip()
    return normalized


def detect_mime_type(data: bytes) -> str | None:
    """Best-effort MIME type detection for arbitrary payloads."""

    global _magic_mime_detector

    if not data:
        return None

    detector: Any | None
    if _magic_mime_detector is _MAGIC_NOT_INITIALIZED:
        detector = None
        if magic is not None:  # pragma: no branch - trivial branch
            try:
                detector = magic.Magic(mime=True)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - depends on runtime env
                logger.warning(
                    "Failed to initialize libmagic MIME detector", exc_info=True
                )
                detector = None
        _magic_mime_detector = detector
    else:
        detector = _magic_mime_detector  # type: ignore[assignment]

    if detector is not None:
        try:
            result = detector.from_buffer(data)  # type: ignore[call-arg]
        except AttributeError:  # pragma: no cover - fallback path
            try:
                result = (
                    magic.from_buffer(data, mime=True) if magic is not None else None
                )
            except Exception:  # pragma: no cover - depends on runtime env
                logger.warning("libmagic failed to detect MIME type", exc_info=True)
                result = None
        except Exception:  # pragma: no cover - depends on runtime env
            logger.warning("libmagic failed to detect MIME type", exc_info=True)
            result = None
        if isinstance(result, bytes):
            detected = result.decode("ascii", "ignore")
        elif isinstance(result, str):
            detected = result
        else:
            detected = ""
        normalized = _normalize_mime_type(detected)
        if normalized:
            return normalized

    # Handle a few lightweight signatures when libmagic is unavailable.
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    # Fall back to lightweight signature checks for common image formats.
    return _normalize_mime_type(_detect_image_mime(data)) or None


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


async def save_image(
    upload: UploadFile, subdir: str, prefix: str, *, locale: str | None = None
) -> str:
    declared_type = (upload.content_type or "").lower()
    if declared_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        )
    data = await _read_limited(upload, MAX_IMAGE_SIZE, locale=locale)
    detected_type = _detect_image_mime(data)
    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        )
    if detected_type != declared_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.content_type_mismatch", locale=locale),
        )
    try:
        optimized_data, optimized_type = await asyncio.to_thread(
            optimize_image,
            data,
            max_width=getattr(settings, "image_max_width", 0),
            max_height=getattr(settings, "image_max_height", 0),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        ) from None

    ext = _PREFERRED_EXTENSIONS.get(optimized_type) or _ext_from_mime(optimized_type)
    name = _gen_name(prefix, ext)
    base = settings.static_dir_path
    sanitized_subdir = subdir.strip("/ ")
    target_dir = base / sanitized_subdir
    await asyncio.to_thread(_ensure_dir, target_dir)
    path = target_dir / name
    await asyncio.to_thread(path.write_bytes, optimized_data)
    # Return canonical public URL without accidental duplicate slashes.
    return f"/static/{sanitized_subdir}/{name}"


async def save_attachment(
    upload: UploadFile, subdir: str, prefix: str, *, locale: str | None = None
) -> str:
    declared_raw = (upload.content_type or "").strip()
    declared_type = _normalize_mime_type(declared_raw)
    allowed_types = settings.event_file_allowed_mime_types_set
    if not declared_type or (allowed_types and declared_type not in allowed_types):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        )

    original_name = upload.filename or ""
    ext = Path(original_name).suffix.lower()
    ext_without_dot = ext[1:] if ext.startswith(".") else ext

    allowed_exts = settings.event_file_allowed_extensions_set

    try:
        limit = int(settings.event_file_max_size_bytes)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        limit = 1
    data = await _read_limited(upload, limit, locale=locale)

    detected_type = detect_mime_type(data) or ""
    if detected_type:
        if allowed_types and detected_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=translate("errors.files.unsupported_type", locale=locale),
            )
        if declared_type and detected_type != declared_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=translate("errors.files.content_type_mismatch", locale=locale),
            )

    def _ext_without_dot_from_mime(mime: str) -> str:
        candidate = _ext_from_mime(mime).lower()
        return candidate[1:] if candidate.startswith(".") else candidate

    detected_ext_without_dot = (
        _ext_without_dot_from_mime(detected_type) if detected_type else ""
    )
    declared_ext_without_dot = (
        _ext_without_dot_from_mime(declared_type) if declared_type else ""
    )

    if (
        detected_ext_without_dot
        and allowed_exts
        and detected_ext_without_dot not in allowed_exts
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_extension", locale=locale),
        )

    candidate_exts: tuple[str, ...] = (
        ext_without_dot,
        detected_ext_without_dot,
        declared_ext_without_dot,
    )
    chosen_ext_without_dot = next(
        (
            candidate
            for candidate in candidate_exts
            if candidate and (not allowed_exts or candidate in allowed_exts)
        ),
        "",
    )

    if not chosen_ext_without_dot and allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_extension", locale=locale),
        )

    if not chosen_ext_without_dot:
        chosen_ext_without_dot = declared_ext_without_dot or detected_ext_without_dot

    ext_for_name = f".{chosen_ext_without_dot}" if chosen_ext_without_dot else ""
    name = _gen_name(prefix, ext_for_name)
    base = settings.static_dir_path
    sanitized_subdir = subdir.strip("/ ")
    target_dir = base / sanitized_subdir
    await asyncio.to_thread(_ensure_dir, target_dir)
    path = target_dir / name
    await scan_for_malware(data, locale=locale)
    await asyncio.to_thread(path.write_bytes, data)
    return f"/static/{sanitized_subdir}/{name}"


def _resolve_static_file_path(file_url: str) -> Path | None:
    if not file_url:
        return None

    parsed = urlparse(file_url)
    raw_path = unquote(parsed.path or "")
    if not raw_path:
        return None

    trimmed = raw_path.lstrip("/")
    if not trimmed:
        return None

    parts = Path(trimmed).parts
    if not parts or parts[0] != "static":
        return None

    relative = Path(*parts[1:])
    if not relative.parts:
        return None

    base = settings.static_dir_path
    base_resolved = base.resolve()
    target = (base_resolved / relative).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        return None
    return target


def _unlink_ignore_missing(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Failed to remove file at %s", path, exc_info=True)


async def delete_static_file(file_url: str) -> None:
    path = _resolve_static_file_path(file_url)
    if path is None:
        return
    await asyncio.to_thread(_unlink_ignore_missing, path)
