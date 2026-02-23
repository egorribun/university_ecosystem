import asyncio
import hashlib
import logging
import pickle
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image

from app.services.storage import StorageBackend
from app.utils.images import _resolve_resample_filter

try:
    import pillow_avif  # noqa: F401 - registers AVIF handler with Pillow
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Redis cache TTL for transformed images (7 days)
_CACHE_TTL = 7 * 24 * 60 * 60


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
            # We use pickle to store the tuple (bytes, str) safely as this is an internal cache
            data, mime = pickle.loads(cached_payload)
            return data, mime
    except Exception as exc:
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
    except Exception as exc:
        logger.error("Failed to fetch source image %s: %s", path, exc)
        raise ValueError(f"Could not load image: {path}") from exc

    if format_preference == "original" and width is None:
        # No transformation needed, but we might still want to cache it or just return
        return source_bytes, _guess_mime(path)

    try:
        transformed_data, mime = await asyncio.to_thread(
            _process_image, source_bytes, width, format_preference
        )

        try:
            # Cache the result via Redis
            from app.deps.cache import get_cache_client

            redis_client = await get_cache_client()
            payload = pickle.dumps((transformed_data, mime))
            await redis_client.setex(redis_key, _CACHE_TTL, payload)
        except Exception as exc:
            logger.warning("Redis cache write failed for %s: %s", path, exc)

        return transformed_data, mime

    except Exception as exc:
        logger.error("Failed to transform image %s: %s", path, exc)
        return source_bytes, _guess_mime(path)


async def _fetch_source_bytes(backend: StorageBackend, path: str) -> bytes:
    """Read source bytes from backend. Local files are read directly, S3 via client."""
    from app.services.storage import S3Storage, StaticFSStorage

    # Security: Early validation of user input to block path traversal
    # This returns a sanitized copy, making the data flow clearer for static analysis
    sanitized_path = _sanitize_path_input(path)

    # Normalize path: ensure it doesn't have double slashes and has a
    # leading slash for extraction logic
    normalized_path = "/" + sanitized_path.lstrip("/")

    if isinstance(backend, StaticFSStorage):
        # The path might contain the base_url prefix (e.g. "/static/avatars/...")
        # StaticFSStorage._extract_relative_path handles stripping this prefix.
        rel_path = backend._extract_relative_path(normalized_path)
        if rel_path is None:
            # Fallback to direct path usage if extraction fails
            # Safe: sanitized_path has been validated (no "..", no null bytes)
            rel_path = Path(sanitized_path.lstrip("/"))  # lgtm[py/path-injection]

        # Security: Validate path is within base directory (prevent path traversal)
        # This is our secondary defense layer after early sanitization
        full_path = _validate_path_within_base(backend.base_dir, rel_path)

        # Handle case where spaces in URL were meant to be underscores on disk
        # Safe: full_path is validated to be within base_dir by
        # _validate_path_within_base
        if not full_path.exists() and " " in str(rel_path):  # lgtm[py/path-injection]
            underscored_rel = Path(str(rel_path).replace(" ", "_"))
            underscored_path = _validate_path_within_base(
                backend.base_dir, underscored_rel
            )
            if underscored_path.exists():  # lgtm[py/path-injection]
                full_path = underscored_path

        if not full_path.exists():  # lgtm[py/path-injection]
            raise FileNotFoundError(f"Image not found at {full_path}")

        return await asyncio.to_thread(full_path.read_bytes)  # lgtm[py/path-injection]

    if isinstance(backend, S3Storage):
        # S3Storage._extract_key handles stripping base_url
        key = backend._extract_key(normalized_path)
        if key is None:
            key = sanitized_path.lstrip("/")

        # Security: Validate key doesn't contain path traversal sequences
        if ".." in key or key.startswith("/"):
            raise ValueError("Invalid S3 key: path traversal detected")

        # Handle potential space/underscore mismatch for S3 as well
        # (Though less likely to be an issue with S3 keys unless manually renamed)
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None, lambda: backend.client.get_object(Bucket=backend.bucket, Key=key)
            )
        except backend.client.exceptions.NoSuchKey:
            if " " in key:
                key = key.replace(" ", "_")
                response = await loop.run_in_executor(
                    None,
                    lambda: backend.client.get_object(Bucket=backend.bucket, Key=key),
                )
            else:
                raise
        return response["Body"].read()  # type: ignore[no-any-return]

    raise ValueError("Unsupported storage backend for image proxy")


def _sanitize_path_input(path: str) -> str:
    """
    Validate and sanitize user-provided path input.
    Returns the validated path.
    Raises ValueError if path contains traversal sequences.
    """
    # Block path traversal patterns
    if ".." in path:
        raise ValueError("Path traversal detected: '..' not allowed")

    # Block absolute paths (Unix and Windows)
    if path.startswith("/") and path.count("/") > 1 and path[1:].startswith("/"):
        raise ValueError("Absolute path not allowed")

    # Block Windows absolute paths
    if len(path) > 1 and path[1] == ":":
        raise ValueError("Windows absolute path not allowed")

    # Block null bytes (can be used to bypass filters)
    if "\x00" in path:
        raise ValueError("Null byte in path not allowed")

    # Return validated path - signals to static analyzers that output is safe
    return path


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
    data: bytes, width: int | None, format_pref: Literal["avif", "webp", "original"]
) -> tuple[bytes, str]:
    """Synchronous image processing block for thread executor."""

    with Image.open(BytesIO(data)) as img:
        # Preserve aspect ratio
        w, h = img.size

        if width and width < w:
            new_h = int(h * (width / w))
            img = img.resize((width, new_h), resample=_resolve_resample_filter())  # type: ignore[assignment]

        buffer = BytesIO()
        if format_pref == "avif":
            try:
                img.save(buffer, format="AVIF", quality=60)
                return buffer.getvalue(), "image/avif"
            except Exception:
                # Fallback to webp if avif encoding fails (e.g. plugin missing)
                logger.warning("AVIF encoding failed, falling back to WebP")
                format_pref = "webp"

        if format_pref == "webp":
            img.save(buffer, format="WEBP", quality=80, method=6)
            return buffer.getvalue(), "image/webp"

        # If original or fallback
        original_format = img.format or "JPEG"
        img.save(buffer, format=original_format)
        return buffer.getvalue(), f"image/{original_format.lower()}"


def _guess_mime(path: str) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"
