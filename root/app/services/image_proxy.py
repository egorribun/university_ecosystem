import asyncio
import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Literal

from diskcache import Cache
from PIL import Image

from app.core.config import settings
from app.services.storage import StorageBackend
from app.utils.images import _resolve_resample_filter

try:
    import pillow_avif  # noqa: F401 - registers AVIF handler with Pillow
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Initialize disk cache for transformed images
_cache_dir = Path(settings.image_proxy_cache_dir)
if not _cache_dir.is_absolute():
    _cache_dir = (Path(__file__).resolve().parents[2] / _cache_dir).resolve()

_cache_dir.mkdir(parents=True, exist_ok=True)

# Cache size limit in bytes (GB -> Bytes)
_size_limit = int(settings.image_proxy_cache_size_gb * 1024 * 1024 * 1024)

# We use a persistent disk cache to store processed images
image_cache = Cache(str(_cache_dir), size_limit=_size_limit)


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

    cached_data = image_cache.get(cache_key)
    if cached_data:
        data, mime = cached_data
        return data, mime

    # If not in cache, fetch from storage backend
    # Note: StorageBackend protocol doesn't have a direct 'get_file_bytes' method in the protocol,
    # but the implementations (StaticFSStorage, S3Storage) effectively work with paths.
    # However, save_file returns a URL. We might need to fetch the file bytes differently.

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

        # Cache the result
        image_cache.set(cache_key, (transformed_data, mime))
        return transformed_data, mime

    except Exception as exc:
        logger.error("Failed to transform image %s: %s", path, exc)
        return source_bytes, _guess_mime(path)


async def _fetch_source_bytes(backend: StorageBackend, path: str) -> bytes:
    """Read source bytes from backend. Local files are read directly, S3 via client."""
    from app.services.storage import S3Storage, StaticFSStorage

    # Normalize path: ensure it doesn't have double slashes and has a leading slash for extraction logic
    normalized_path = "/" + path.lstrip("/")

    if isinstance(backend, StaticFSStorage):
        # The path might contain the base_url prefix (e.g. "/static/avatars/...")
        # StaticFSStorage._extract_relative_path handles stripping this prefix.
        rel_path = backend._extract_relative_path(normalized_path)
        if rel_path is None:
            # Fallback to direct path usage if extraction fails
            rel_path = Path(path.lstrip("/"))

        # Security: Validate path is within base directory (prevent path traversal)
        full_path = _validate_path_within_base(backend.base_dir, rel_path)

        # Handle case where spaces in URL were meant to be underscores on disk
        if not full_path.exists() and " " in str(rel_path):
            underscored_rel = Path(str(rel_path).replace(" ", "_"))
            underscored_path = _validate_path_within_base(backend.base_dir, underscored_rel)
            if underscored_path.exists():
                full_path = underscored_path

        if not full_path.exists():
            raise FileNotFoundError(f"Image not found at {full_path}")

        return await asyncio.to_thread(full_path.read_bytes)

    if isinstance(backend, S3Storage):
        # S3Storage._extract_key handles stripping base_url
        key = backend._extract_key(normalized_path)
        if key is None:
            key = path.lstrip("/")

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
        return response["Body"].read()

    raise ValueError("Unsupported storage backend for image proxy")


def _validate_path_within_base(base_dir: Path, rel_path: Path) -> Path:
    """
    Validate that the resolved path stays within base_dir.
    Prevents path traversal attacks (e.g., using '../' to escape).
    """
    # Resolve to absolute path to handle any '..' or '.' in the path
    full_path = (base_dir / rel_path).resolve()
    base_resolved = base_dir.resolve()

    # Check that the resolved path is within the base directory
    try:
        full_path.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {rel_path}")

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
            img = img.resize((width, new_h), resample=_resolve_resample_filter())

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
