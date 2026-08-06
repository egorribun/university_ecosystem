"""Image processing helpers for uploaded files.

This module uses pyvips when available (10x faster than Pillow) with
automatic fallback to Pillow for Windows or when pyvips is not installed.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, cast

from defusedxml.ElementTree import fromstring as parse_svg_string
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.logging import get_logger

# Try to use pyvips for 10x faster processing
# Catch ImportError (not installed) and OSError (libvips missing at runtime)
try:
    from app.utils.images_vips import VIPS_AVAILABLE, optimize_image_vips
except (ImportError, OSError):  # RZ-28-01
    VIPS_AVAILABLE = False
    optimize_image_vips = None  # type: ignore[assignment]

logger = get_logger(__name__)

try:  # Pillow >= 9.1 exposes the resampling enum in PIL.Image
    from PIL.Image import Resampling
except ImportError:  # pragma: no cover
    Resampling: Any = int  # type: ignore[no-redef]


def _resolve_resample_filter() -> Resampling:
    """Return the best available high-quality resampling filter."""
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return cast("Resampling", resampling.LANCZOS)
    lanczos = getattr(Image, "LANCZOS", None)  # pragma: no cover
    if lanczos is None:  # pragma: no cover
        raise AttributeError("Pillow installation does not expose a LANCZOS filter")
    return cast("Resampling", lanczos)  # pragma: no cover


def sanitize_svg(data: bytes) -> bytes:
    """Validate and sanitize SVG data to prevent XXE and other XML-based attacks."""
    try:
        # defusedxml will raise an error if it finds any suspicious XML
        parse_svg_string(data)
        return data
    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain ValueError for invalid or malicious SVG data
        raise ValueError("Invalid or malicious SVG data") from exc


def _optimize_image_pillow(
    data: bytes,
    *,
    max_width: int,
    max_height: int,
) -> tuple[bytes, str]:
    """Process image using Pillow (fallback when pyvips unavailable)."""
    with Image.open(BytesIO(data)) as src_img:
        img: Image.Image = src_img
        if exif_transposed := ImageOps.exif_transpose(img):
            img = exif_transposed
        width, height = img.size

        if width > max_width or height > max_height:
            resample = _resolve_resample_filter()
            img.thumbnail((max_width, max_height), resample=resample)

        buffer = BytesIO()
        img.save(buffer, format="WEBP", method=6, quality=85, lossless=False)

    return buffer.getvalue(), "image/webp"


def optimize_image(
    data: bytes,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
    content_type: str | None = None,
) -> tuple[bytes, str]:
    """Resize and re-encode an image to an optimized WebP payload.

    Uses pyvips when available (10x faster), falls back to Pillow.
    The helper ensures the image fits within the configured bounding box,
    strips EXIF metadata, and converts to WebP format.
    """
    # Handle SVG separately (no raster processing needed)
    if content_type == "image/svg+xml" or data.lstrip().startswith(b"<svg"):
        return sanitize_svg(data), "image/svg+xml"

    # Resolve dimensions with sensible defaults
    max_w = int(max_width or 1920)
    max_h = int(max_height or 1920)
    if max_w <= 0:
        max_w = 1920
    if max_h <= 0:
        max_h = 1920

    # Try pyvips first (10x faster when available)
    if VIPS_AVAILABLE and optimize_image_vips is not None:
        try:
            return optimize_image_vips(
                data,
                max_width=max_w,
                max_height=max_h,
                quality=85,
            )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — pyvips failure falls back to Pillow (reviewed TD-27-04)
            logger.warning("pyvips failed, falling back to Pillow: %s", exc)

    # Pillow fallback
    try:
        return _optimize_image_pillow(data, max_width=max_w, max_height=max_h)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Invalid image data") from exc
