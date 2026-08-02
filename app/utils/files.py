import asyncio
import mimetypes
import re
import secrets
from pathlib import Path
from typing import Any, Final

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.localization import translate
from app.core.logging import get_logger
from app.services.file_scanner import scan_for_malware
from app.services.storage import StaticFSStorage, StorageBackend, get_storage_backend

logger = get_logger(__name__)


def optimize_image(*args: Any, **kwargs: Any) -> Any:
    """Load the Pillow-backed optimizer only when an image is actually saved.

    Keeping this compatibility wrapper at module scope preserves the existing
    test/extension patch seam while preventing MIME and attachment-only callers
    from importing Pillow during application startup.
    """

    from app.utils.images import optimize_image as _optimize_image

    return _optimize_image(*args, **kwargs)


storage_backend = get_storage_backend(settings)
_default_storage_backend = storage_backend


def _storage_backend_signature() -> tuple[object, ...]:
    """Return a tuple describing settings that affect storage backend selection."""

    return (
        settings.storage_backend,
        getattr(settings, "static_dir_path", None),
        getattr(settings, "storage_static_base_url", None),
        getattr(settings, "storage_s3_bucket", None),
        getattr(settings, "storage_s3_region", None),
        getattr(settings, "storage_s3_access_key_id", None),
        getattr(settings, "storage_s3_secret_access_key", None),
        getattr(settings, "storage_s3_endpoint_url", None),
        getattr(settings, "storage_s3_base_url", None),
    )


_storage_backend_snapshot = _storage_backend_signature()


def _get_storage_backend() -> StorageBackend:
    """Return the configured storage backend, refreshing when settings change."""

    global storage_backend, _default_storage_backend, _storage_backend_snapshot

    if storage_backend is _default_storage_backend:
        signature = _storage_backend_signature()
        if signature != _storage_backend_snapshot:
            storage_backend = get_storage_backend(settings)
            _default_storage_backend = storage_backend
            _storage_backend_snapshot = signature
    return storage_backend


def _ensure_dir(path: Path) -> None:
    """Ensure ``path`` exists on disk."""

    path.mkdir(parents=True, exist_ok=True)


async def _prepare_local_storage(backend: StorageBackend, subdir: str) -> None:
    """Create the subdirectory for static storage if using the filesystem backend."""

    if isinstance(backend, StaticFSStorage):
        target = backend.base_dir
        if subdir:
            target = target / subdir
        await asyncio.to_thread(_ensure_dir, target)


ALLOWED_IMAGE_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_IMAGE_SIZE: Final[int] = 5 * 1024 * 1024

_PREFIX_CLEAN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PREFERRED_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# python-magic is imported lazily inside detect_mime_type to avoid hanging on
# Windows when libmagic.dll is missing (ImportError is not raised — the import
# blocks indefinitely against a missing DLL).
_MAGIC_NOT_INITIALIZED: Final[object] = object()
_magic_mime_detector: Any = _MAGIC_NOT_INITIALIZED
_magic_module: Any = None  # Populated on first successful import


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
    # Basic SVG detection
    if data.lstrip().startswith(b"<svg") or b"<svg" in data[:1024].lower():
        return "image/svg+xml"
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

    global _magic_mime_detector, _magic_module

    if not data:
        return None

    detector: Any | None
    if _magic_mime_detector is _MAGIC_NOT_INITIALIZED:
        detector = None
        try:
            import magic as _magic_import

            _magic_module = _magic_import
            detector = _magic_import.Magic(mime=True)
        except Exception:  # pragma: no cover - ImportError or OSError on missing DLL  # RZ-22-01-JUSTIFIED: optional dependency — libmagic may not be installed (reviewed TD-27-04)
            logger.warning("Failed to initialize libmagic MIME detector", exc_info=True)
            detector = None
        _magic_mime_detector = detector
    else:
        detector = _magic_mime_detector

    if detector is not None:
        try:
            result = detector.from_buffer(data)
        except AttributeError:
            try:
                result = (
                    _magic_module.from_buffer(data, mime=True)
                    if _magic_module is not None
                    else None
                )
            except Exception:  # pragma: no cover - depends on runtime env  # RZ-22-01-JUSTIFIED: optional dependency — libmagic API varies by version (reviewed TD-27-04)
                logger.warning("libmagic failed to detect MIME type", exc_info=True)
                result = None
        except Exception:  # pragma: no cover - depends on runtime env  # RZ-22-01-JUSTIFIED: optional dependency — libmagic may raise various errors (reviewed TD-27-04)
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

    lowered = data[:2048].lower()
    if b"<svg" in lowered:
        return "image/svg+xml"

    # Fall back to lightweight signature checks for common image formats.
    return _normalize_mime_type(_detect_image_mime(data)) or None


def _looks_like_polyglot(data: bytes, detected_type: str) -> bool:
    # FILE-2 (audit 2026-03): Expand SVG XSS pattern set and scan full content.
    #
    # Previous issues:
    # 1. Only checked first 4096 bytes — crafted files can embed payloads deeper.
    # 2. SVG check only matched <script> and onload= — missed many valid attack
    #    vectors: <image onerror>, <animate>, <use xlink:href=javascript:>,
    #    <foreignObject>, data: URI in href, base64-encoded <script>, etc.
    # 3. No check that SVG file actually starts with valid SVG structure.

    # Scan the full content (SVGs should be small; PDFs need full scan too).
    lowered = data.lower()
    lowered_head = lowered[:4096]

    if detected_type == "application/pdf":
        if b"<script" in lowered or b"<svg" in lowered:
            return True

    if detected_type == "image/svg+xml":
        # 1. Must actually contain an <svg> root element.
        if b"<svg" not in lowered_head:
            return True  # Claims to be SVG but isn't — treat as polyglot.

        # 2. Comprehensive XSS/execution patterns in SVG:
        _SVG_DANGEROUS_PATTERNS: tuple[bytes, ...] = (
            b"<script",  # Direct script tag
            b"onerror=",  # <image onerror="…">, <img onerror="…">
            b"onload=",  # <body onload>, <svg onload>
            b"onclick=",  # Click handlers
            b"onmouseover=",  # Hover handlers
            b"onfocus=",  # Focus handlers
            b"onbegin=",  # SMIL animation event
            b"onend=",  # SMIL animation end event
            b"onrepeat=",  # SMIL repeat event
            b"<animate ",  # SMIL animate (can set event attrs)
            b"<set ",  # SMIL set (can set event attrs)
            b"<foreignobject",  # Embeds arbitrary HTML into SVG
            b"<use ",  # xlink:href can reference external SVGs
            b"javascript:",  # javascript: URI in href/src
            b"data:text/html",  # data: URI embedding HTML
            b"data:text/xml",  # data: URI embedding XML
            b"vbscript:",  # IE VBScript URI
            b"xlink:href",  # Can reference external resources
            b"&#",  # HTML entity encoding (obfuscation)
            b"base64,",  # Base64 encoded payload
        )
        for pattern in _SVG_DANGEROUS_PATTERNS:
            if pattern in lowered:
                return True

    return bool(b"<script" in lowered and b"<!doctype html" in lowered_head)


async def _quarantine_payload(
    data: bytes,
    *,
    subdir: str,
    prefix: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    metadata = metadata or {}
    backend = _get_storage_backend()
    cleaned = subdir.strip("/ ")
    quarantine_subdir = f"quarantine/{cleaned}" if cleaned else "quarantine"
    await _prepare_local_storage(backend, quarantine_subdir)
    name = _gen_name(f"{prefix}_{reason}", ".bin")
    relative_path = f"{quarantine_subdir}/{name}" if quarantine_subdir else name
    try:
        await backend.save_file(
            relative_path,
            data,
            content_type="application/octet-stream",
        )
    except (
        OSError,
        ConnectionError,
    ) as exc:  # RZ-22-01: narrowed — file/network storage errors
        logger.warning(
            "Failed to store quarantined payload: %s",
            exc,
            exc_info=True,
            extra=metadata,
        )


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
    if _looks_like_polyglot(data, detected_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        )
    try:
        optimized_data, optimized_type = await asyncio.to_thread(
            optimize_image,
            data,
            max_width=getattr(settings, "image_max_width", 0),
            max_height=getattr(settings, "image_max_height", 0),
            content_type=detected_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                str(exc)
                if str(exc)
                else translate("errors.files.unsupported_type", locale=locale)
            ),
        ) from None

    ext = _PREFERRED_EXTENSIONS.get(optimized_type) or _ext_from_mime(optimized_type)
    name = _gen_name(prefix, ext)
    sanitized_subdir = subdir.strip("/ ")
    backend = _get_storage_backend()
    await _prepare_local_storage(backend, sanitized_subdir)
    relative_path = f"{sanitized_subdir}/{name}" if sanitized_subdir else name
    # Use aggressive caching for all optimized images
    cache_control = "public, max-age=31536000, immutable"
    return await backend.save_file(
        relative_path,
        optimized_data,
        content_type=optimized_type,
        cache_control=cache_control,
    )


async def save_attachment(
    upload: UploadFile,
    subdir: str,
    prefix: str,
    *,
    locale: str | None = None,
    allowed_mime_types: set[str] | None = None,
    allowed_extensions: set[str] | None = None,
    max_size_bytes: int | None = None,
    return_meta: bool = False,
) -> str | dict[str, object]:
    declared_raw = (upload.content_type or "").strip()
    declared_type = _normalize_mime_type(declared_raw)
    allowed_types = (
        allowed_mime_types
        if allowed_mime_types is not None
        else settings.event_file_allowed_mime_types_set
    )
    if declared_type and allowed_types and declared_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=translate("errors.files.unsupported_type", locale=locale),
        )

    original_name = upload.filename or ""
    ext = Path(original_name).suffix.lower()
    ext_without_dot = ext[1:] if ext.startswith(".") else ext

    allowed_exts = (
        allowed_extensions
        if allowed_extensions is not None
        else settings.event_file_allowed_extensions_set
    )

    try:
        limit = int(max_size_bytes if max_size_bytes is not None else 0)
    except (TypeError, ValueError):  # RZ-28-01
        limit = 0
    if limit <= 0:
        try:
            limit = int(settings.event_file_max_size_bytes)
        except (TypeError, ValueError):  # RZ-28-01
            limit = 0
    if limit <= 0:
        limit = 1
    data = await _read_limited(upload, limit, locale=locale)

    detected_type = detect_mime_type(data) or ""
    metadata: dict[str, Any] = {
        "declared_type": declared_type or None,
        "detected_type": detected_type or None,
        "filename_extension": ext_without_dot or None,
        "allowed_types": sorted(allowed_types) if allowed_types else None,
        "allowed_extensions": sorted(allowed_exts) if allowed_exts else None,
    }

    async def _quarantine_and_raise(
        detail_key: str, status_code_value: int, *, reason: str
    ) -> None:
        await _quarantine_payload(
            data,
            subdir=subdir,
            prefix=prefix,
            reason=reason,
            metadata=metadata,
        )
        raise HTTPException(
            status_code=status_code_value,
            detail=translate(detail_key, locale=locale),
        )

    if not detected_type:
        await _quarantine_and_raise(
            "errors.files.unsupported_type",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            reason="unknown-mime",
        )

    if allowed_types and detected_type not in allowed_types:
        await _quarantine_and_raise(
            "errors.files.unsupported_type",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            reason="blocked-mime",
        )

    if declared_type and declared_type != detected_type:
        await _quarantine_and_raise(
            "errors.files.content_type_mismatch",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            reason="content-mismatch",
        )

    if _looks_like_polyglot(data, detected_type):
        await _quarantine_and_raise(
            "errors.files.unsupported_type",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            reason="polyglot-detected",
        )

    def _ext_without_dot_from_mime(mime: str) -> str:
        candidate = _ext_from_mime(mime).lower()
        return candidate[1:] if candidate.startswith(".") else candidate

    detected_ext_without_dot = _ext_without_dot_from_mime(detected_type)
    declared_ext_without_dot = (
        _ext_without_dot_from_mime(declared_type) if declared_type else ""
    )
    chosen_ext_without_dot = detected_ext_without_dot or declared_ext_without_dot

    if allowed_exts:
        candidates = (
            detected_ext_without_dot,
            declared_ext_without_dot,
            ext_without_dot,
        )
        chosen_ext_without_dot = next(
            (candidate for candidate in candidates if candidate in allowed_exts), ""
        )
        if not chosen_ext_without_dot:
            await _quarantine_and_raise(
                "errors.files.unsupported_extension",
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                reason="blocked-extension",
            )
    else:
        if not chosen_ext_without_dot:
            fallback_exts = (ext_without_dot,)
            chosen_ext_without_dot = next(
                (candidate for candidate in fallback_exts if candidate),
                "",
            )

    ext_for_name = f".{chosen_ext_without_dot}" if chosen_ext_without_dot else ""
    name = _gen_name(prefix, ext_for_name)
    await scan_for_malware(
        data,
        locale=locale,
        size_bytes=len(data),
        quarantine_payload=data,
        quarantine_handler=lambda payload, signature: _quarantine_payload(
            payload,
            subdir=subdir,
            prefix=prefix,
            reason=f"signature-{signature or 'unknown'}",
            metadata={**metadata, "signature": signature},
        ),
    )
    sanitized_subdir = subdir.strip("/ ")
    backend = _get_storage_backend()
    await _prepare_local_storage(backend, sanitized_subdir)
    relative_path = f"{sanitized_subdir}/{name}" if sanitized_subdir else name
    # Use aggressive caching for attachments as well
    cache_control = "public, max-age=31536000, immutable"
    url = await backend.save_file(
        relative_path,
        data,
        content_type=declared_type or detected_type,
        cache_control=cache_control,
    )
    if return_meta:
        return {
            "url": url,
            "content_type": declared_type or detected_type,
            "size": len(data),
            "filename": upload.filename or name,
            "detected_type": detected_type,
        }
    return url


async def delete_static_file(file_url: str) -> None:
    backend = _get_storage_backend()
    await backend.delete_file(file_url)
