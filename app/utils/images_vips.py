"""Image processing using pyvips for high performance.

pyvips is a Python binding for libvips, a fast image processing library.
It is typically 10x faster than Pillow for common operations like resize
and format conversion, with significantly lower memory usage.

This module provides an alternative implementation that is used when
pyvips is available, with automatic fallback to Pillow.

Note: pyvips requires libvips to be installed at the system level:
    - Docker: apt-get install libvips-dev
    - macOS: brew install vips
    - Windows: Not recommended (use Pillow fallback)
"""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

# Try to import pyvips, but don't fail if unavailable
# Catch both ImportError (pyvips not installed) and OSError (libvips not found)
try:
    import pyvips

    VIPS_AVAILABLE = True
    logger.debug("pyvips available, using high-performance image processing")
except (ImportError, OSError) as exc:
    VIPS_AVAILABLE = False
    pyvips = None
    logger.debug(
        "pyvips not available (%s), will use Pillow fallback", type(exc).__name__
    )


def optimize_image_vips(
    data: bytes,
    *,
    max_width: int = 1920,
    max_height: int = 1920,
    quality: int = 85,
) -> tuple[bytes, str]:
    """Process and optimize image using pyvips (10x faster than Pillow).

    Args:
        data: Raw image bytes
        max_width: Maximum width (will shrink proportionally)
        max_height: Maximum height (will shrink proportionally)
        quality: WebP quality (1-100)

    Returns:
        Tuple of (optimized image bytes, mime type)

    Raises:
        ValueError: If image cannot be processed
    """
    if not VIPS_AVAILABLE:
        raise RuntimeError("pyvips is not available")

    try:
        # Load image from buffer with auto-rotation based on EXIF
        # thumbnail_buffer is optimized for this use case
        image = pyvips.Image.thumbnail_buffer(
            data,
            max_width,
            height=max_height,
            size=pyvips.enums.Size.DOWN,  # Only shrink, never enlarge
        )

        # Auto-rotate based on EXIF orientation and strip metadata
        image = image.autorot()

        # Save as WebP with good quality/size balance
        # effort=4 is a good balance between speed and compression
        buffer = image.webpsave_buffer(
            Q=quality,
            effort=4,
            strip=True,  # Strip metadata for smaller files
        )

        return bytes(buffer), "image/webp"

    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain — converts pyvips errors to ValueError (reviewed TD-27-04)
        logger.warning("pyvips processing failed: %s", exc)
        raise ValueError(f"Failed to process image with pyvips: {exc}") from exc


def get_image_dimensions_vips(data: bytes) -> tuple[int, int]:
    """Get image dimensions using pyvips (faster than Pillow).

    Args:
        data: Raw image bytes

    Returns:
        Tuple of (width, height)
    """
    if not VIPS_AVAILABLE:
        raise RuntimeError("pyvips is not available")

    image = pyvips.Image.new_from_buffer(data, "")
    return image.width, image.height


__all__ = [
    "VIPS_AVAILABLE",
    "get_image_dimensions_vips",
    "optimize_image_vips",
]
