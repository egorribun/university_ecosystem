import asyncio
import hashlib
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote

from app.core.logging import get_logger

# msgspec is used for safe binary serialization of Redis cache payloads.
# Unlike pickle, msgspec cannot execute arbitrary code on deserialization —
# a compromised Redis cannot achieve RCE. (RZ-1: audit 2026-02-26)
try:
    import msgspec.msgpack as _msgpack

    def _cache_encode(data: bytes, mime: str) -> bytes:
        return bytes(_msgpack.encode({"d": data, "m": mime}))

    def _cache_decode(payload: bytes) -> tuple[bytes, str]:
        obj = _msgpack.decode(payload)
        return bytes(obj["d"]), str(obj["m"])

except ImportError:
    # json + base64 as a safe fallback (no pickle in any code path)
    import base64
    import json

    def _cache_encode(data: bytes, mime: str) -> bytes:
        return json.dumps({"d": base64.b64encode(data).decode(), "m": mime}).encode()

    def _cache_decode(payload: bytes) -> tuple[bytes, str]:
        obj = json.loads(payload)
        return base64.b64decode(obj["d"]), str(obj["m"])


from PIL import Image

from app.core.config import settings
from app.services.storage import StorageBackend
from app.utils.images import (
    ImagePixelLimitError,
    _resolve_resample_filter,
    validate_image_dimensions,
)

try:
    import pillow_avif  # noqa: F401 - registers AVIF handler with Pillow
except ImportError:
    pass

logger = get_logger(__name__)

# Bound retained transformed bytes to one day. User media is revalidated on
# every cache hit, but expired entries should not linger in Redis for a week.
_CACHE_TTL = 24 * 60 * 60


def _configured_image_max_pixels() -> int:
    """Return the bounded image pixel budget used by proxy transformations."""
    from app.utils.images import DEFAULT_MAX_IMAGE_PIXELS

    configured = getattr(settings, "image_max_pixels", None)
    if configured is None:
        return DEFAULT_MAX_IMAGE_PIXELS
    # ``StorageSettings`` validates this field as an integer.  Keep the
    # defensive fallback for lightweight test/config objects without using a
    # runtime-no-op typing cast that can hide invalid values.
    if not isinstance(configured, int) or configured == 0:
        return DEFAULT_MAX_IMAGE_PIXELS
    return configured


def _validate_image_payload(data: bytes, *, max_pixels: int) -> None:
    """Validate raster dimensions without turning malformed legacy bytes into 500s."""
    try:
        with Image.open(BytesIO(data)) as image:
            validate_image_dimensions(*image.size, max_pixels=max_pixels)
    except ImagePixelLimitError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImagePixelLimitError.from_decompression_bomb(max_pixels) from exc
    except OSError:
        # Existing proxy behavior maps corrupt/missing image data to a safe
        # fallback/404.  The explicit pixel-limit error remains fail-closed.
        return


async def get_transformed_image(
    backend: StorageBackend,
    path: str,
    width: int | None = None,
    format_preference: Literal["avif", "webp", "original"] = "original",
) -> tuple[bytes, str]:
    """
    Fetch image from backend, transform it (resize, re-encode), and return bytes + mime.
    Utilizes disk caching for efficiency.
    """

    # Construct a cache key based on path, width, and format
    cache_key = hashlib.sha256(
        f"{path}:{width}:{format_preference}".encode()
    ).hexdigest()
    redis_key = f"image_proxy:{cache_key}"

    try:
        from app.deps.cache import get_cache_client

        redis_client = await get_cache_client()
        cached_payload = await redis_client.get(redis_key)
        if cached_payload:
            # A deleted user image must not remain publicly retrievable merely
            # because its transformed bytes are still present in Redis.
            source_path = "/" + _sanitize_path_input(path).lstrip("/")
            if not await backend.exists(source_path):
                try:
                    await redis_client.delete(redis_key)
                except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
                    logger.warning("Redis stale image eviction failed: %s", exc)
                raise ValueError(f"Could not load image: {path}")
            # Safe deserialization via msgspec — no code execution risk.
            data, mime = _cache_decode(cached_payload)
            _validate_image_payload(data, max_pixels=_configured_image_max_pixels())
            return data, mime
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
        # RZ-20-04: Narrowed from bare Exception — Redis unavailability.
        logger.warning("Redis cache read failed for %s: %s", path, exc)
    # Note: StorageBackend protocol doesn't have a direct 'get_file_bytes'
    # method in the protocol,
    # but the implementations (StaticFSStorage, S3Storage) effectively work
    # with paths.
    # However, save_file returns a URL. We might need to fetch the file
    # bytes differently.

    # We need a way to get file bytes from the backend or direct from disk/S3
    # Let's add a helper or look for one.
    # Since we can't easily modify the StorageBackend protocol right now,
    # we'll implement a dedicated fetcher here based on backend type.

    try:
        source_bytes = await _fetch_source_bytes(backend, path)
    except (FileNotFoundError, OSError, ConnectionError) as exc:
        # RZ-20-04: Narrowed — storage backend I/O errors.
        logger.error("Failed to fetch source image %s: %s", path, exc)
        raise ValueError(f"Could not load image: {path}") from exc

    if format_preference == "original" and width is None:
        # No transformation is needed, but original mode still cannot bypass
        # the application-level decompression/resource boundary.
        _validate_image_payload(
            source_bytes,
            max_pixels=_configured_image_max_pixels(),
        )
        return source_bytes, _guess_mime(path)

    try:
        transformed_data, mime = await asyncio.to_thread(
            _process_image,
            source_bytes,
            width,
            format_preference,
            _configured_image_max_pixels(),
        )

        try:
            # Cache the result via Redis
            from app.deps.cache import get_cache_client

            redis_client = await get_cache_client()
            payload = _cache_encode(transformed_data, mime)
            await redis_client.setex(redis_key, _CACHE_TTL, payload)
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
            # RZ-20-04: Narrowed — Redis write failure is non-fatal.
            logger.warning("Redis cache write failed for %s: %s", path, exc)

        return transformed_data, mime

    except ImagePixelLimitError:
        raise
    except (OSError, ValueError) as exc:
        # RZ-20-04: Narrowed — PIL/image transformation errors.
        logger.error("Failed to transform image %s: %s", path, exc)
        return source_bytes, _guess_mime(path)


async def _fetch_source_bytes(backend: StorageBackend, path: str) -> bytes:
    """Read source bytes from backend.

    RZ-2 (audit 2026-03-05): Uses the abstract backend.read_file() method
    instead of branching on implementation types. This preserves SRP and
    eliminates brittle hacks involving internal client access.
    """
    # Security: Early validation of user input to block path traversal.
    sanitized_path = _sanitize_path_input(path)

    # Normalize path: ensure it doesn't have double slashes and has a
    # leading slash for extraction logic if needed by the backend.
    normalized_path = "/" + sanitized_path.lstrip("/")

    try:
        return await backend.read_file(normalized_path)
    except FileNotFoundError:
        # Fallback for potential space/underscore mismatch
        if " " in normalized_path:
            underscored = normalized_path.replace(" ", "_")
            return await backend.read_file(underscored)
        raise


def _sanitize_path_input(path: str) -> str:
    """Validate and sanitize user-provided path input.

    FILE-1 (audit 2026-03): The previous implementation only caught `//`
    double-slash absolute paths and did NOT URL-decode before checking, so
    `%2fetc%2fpasswd` and `/etc/passwd` both bypassed the guard.

    New strategy:
    1. URL-decode the raw input first (catches %2e%2e, %2f, %00, etc.)
    2. Reject null bytes (only possible in the raw form or decoded form)
    3. Use PurePosixPath to normalize and detect traversal beyond root
    4. Block any path whose normalized form is absolute or contains `..`
       components even after normalization

    Returns the cleaned relative path string.
    Raises ValueError if the path is malicious.
    """
    # Step 1: URL-decode iteratively to catch multi-encoded sequences
    decoded = path
    while True:
        prev = decoded
        decoded = unquote(decoded)
        if decoded == prev:
            break

    # Step 2: Block null bytes in both raw and decoded forms
    if "\x00" in path or "\x00" in decoded:
        raise ValueError("Null byte in path not allowed")

    # Step 3: Normalize via PurePosixPath (handles ., .., redundant slashes)
    try:
        normalized = PurePosixPath(decoded)
    except (TypeError, ValueError) as exc:
        # RZ-20-04: Narrowed — PurePosixPath parsing errors.
        raise ValueError(f"Invalid path: {exc}") from exc

    # Step 4: Reject paths that contain `..` components.
    # Absolute URL paths like /static/... are allowed — _validate_path_within_base
    # enforces the filesystem boundary as a second-line defence.
    # PurePosixPath.parts includes '..' literally (no filesystem resolution).
    for part in normalized.parts:
        if part == "..":
            raise ValueError("Path traversal detected: '..' not allowed")

    # Step 6: Block Windows absolute paths (C:\...) in the decoded form
    if len(decoded) > 1 and decoded[1] == ":":
        raise ValueError("Windows absolute path not allowed")

    # Return the raw (but decoded) path — the caller's _validate_path_within_base
    # does a full .resolve() + relative_to() check as a second line of defence.
    return decoded


def _validate_path_within_base(base_dir: Path, rel_path: Path) -> Path:
    """
    Validate that the resolved path stays within base_dir.
    Prevents path traversal attacks (e.g., using '../' to escape).
    """
    # Resolve to absolute path to handle any '..' or '.' in the path
    # Safe: input is pre-validated by _sanitize_path_input (no "..", null bytes, etc.)
    full_path = (base_dir / rel_path).resolve()  # lgtm[py/path-injection]
    base_resolved = base_dir.resolve()

    # Check that the resolved path is within the base directory
    try:
        full_path.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"Path traversal attempt detected: {rel_path}") from exc

    return full_path


def _process_image(
    data: bytes,
    width: int | None,
    format_pref: Literal["avif", "webp", "original"],
    max_pixels: int | None = None,
) -> tuple[bytes, str]:
    """Synchronous image processing block for thread executor."""

    resolved_max_pixels = max_pixels or _configured_image_max_pixels()
    try:
        with Image.open(BytesIO(data)) as img:
            validate_image_dimensions(*img.size, max_pixels=resolved_max_pixels)
            # Preserve aspect ratio
            w, h = img.size
            output_img: Image.Image = img

            if width and width < w:
                new_h = int(h * (width / w))
                # LOW-W19: img.resize() returns a new Image object.  Keep the
                # source image bound to the context manager and close it before
                # switching the output reference so the resized object is not
                # accidentally closed by the source context manager.
                _resized = img.resize(
                    (width, new_h), resample=_resolve_resample_filter()
                )
                img.close()
                output_img = _resized

            buffer = BytesIO()
            if format_pref == "avif":
                try:
                    output_img.save(buffer, format="AVIF", quality=60)
                    return buffer.getvalue(), "image/avif"
                except (OSError, ValueError):
                    # RZ-20-04: Narrowed — AVIF plugin missing or encoding error.
                    logger.warning("AVIF encoding failed, falling back to WebP")
                    format_pref = "webp"

            if format_pref == "webp":
                output_img.save(buffer, format="WEBP", quality=80, method=6)
                return buffer.getvalue(), "image/webp"

            # If original or fallback
            original_format = output_img.format or "JPEG"
            output_img.save(buffer, format=original_format)
            return buffer.getvalue(), f"image/{str(original_format).lower()}"
    except Image.DecompressionBombError as exc:
        raise ImagePixelLimitError.from_decompression_bomb(resolved_max_pixels) from exc


def _guess_mime(path: str) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"
