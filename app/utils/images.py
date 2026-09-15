"""Image processing helpers for uploaded files.

This module uses pyvips when available (10x faster than Pillow) with
automatic fallback to Pillow for Windows or when pyvips is not installed.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

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

# Application-level decompression/resource guard. Decoder-specific limits are
# not a substitute for a policy boundary: both Pillow and libvips may inspect
# image metadata before their own bomb protection is applied.
DEFAULT_MAX_IMAGE_PIXELS = 25_000_000
MAX_CONFIGURED_IMAGE_PIXELS = 100_000_000


class ImagePixelLimitError(ValueError):
    """Raised when an image's declared raster area exceeds policy."""

    def __init__(
        self,
        width: int | None,
        height: int | None,
        max_pixels: int,
    ) -> None:
        self.width = width
        self.height = height
        self.max_pixels = max_pixels
        if width is None:
            message = f"image exceeds pixel budget of {max_pixels}"
        else:
            message = (
                f"image dimensions {width}x{height} exceed pixel budget of {max_pixels}"
            )
        super().__init__(message)

    @classmethod
    def from_decompression_bomb(cls, max_pixels: int) -> ImagePixelLimitError:
        """Normalize Pillow's decoder-level bomb without leaking decoder details."""
        return cls(None, None, max_pixels)


def validate_image_dimensions(
    width: int, height: int, *, max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS
) -> None:
    """Validate positive dimensions and an inclusive raster-area budget."""
    try:
        width_int = int(width)
        height_int = int(height)
        budget = int(max_pixels)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Image dimensions must be finite integers") from exc

    if width_int <= 0 or height_int <= 0:
        raise ValueError("Image dimensions must be positive")
    if budget <= 0:
        raise ValueError("Image pixel budget must be positive")

    # Division avoids constructing a potentially huge product supplied by an
    # untrusted decoder while preserving an exact inclusive boundary.
    if width_int > budget // height_int:
        raise ImagePixelLimitError(width_int, height_int, budget)


try:  # Pillow >= 9.1 exposes the resampling enum in PIL.Image
    from PIL.Image import Resampling
except ImportError:
    Resampling: Any = int  # type: ignore[no-redef]


def _resolve_resample_filter() -> Resampling:
    """Return the best available high-quality resampling filter."""
    resampling: type[Resampling] | None = getattr(Image, "Resampling", None)
    if resampling is not None:
        return resampling.LANCZOS
    lanczos: Resampling | None = getattr(Image, "LANCZOS", None)
    if lanczos is None:
        raise AttributeError("Pillow installation does not expose a LANCZOS filter")
    return lanczos


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
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> tuple[bytes, str]:
    """Process image using Pillow (fallback when pyvips unavailable)."""
    try:
        with Image.open(BytesIO(data)) as src_img:
            # Check header dimensions before EXIF transpose or any pixel operation.
            validate_image_dimensions(*src_img.size, max_pixels=max_pixels)
            img: Image.Image = src_img
            if exif_transposed := ImageOps.exif_transpose(img):
                img = exif_transposed
            width, height = img.size
            validate_image_dimensions(width, height, max_pixels=max_pixels)

            if width > max_width or height > max_height:
                resample = _resolve_resample_filter()
                img.thumbnail((max_width, max_height), resample=resample)

            buffer = BytesIO()
            img.save(buffer, format="WEBP", method=6, quality=85, lossless=False)
    except Image.DecompressionBombError as exc:
        raise ImagePixelLimitError.from_decompression_bomb(max_pixels) from exc

    return buffer.getvalue(), "image/webp"


def optimize_image(
    data: bytes,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
    max_pixels: int | None = None,
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
    pixel_budget = int(max_pixels or DEFAULT_MAX_IMAGE_PIXELS)
    if pixel_budget <= 0 or pixel_budget > MAX_CONFIGURED_IMAGE_PIXELS:
        raise ValueError(
            f"Image pixel budget must be between 1 and {MAX_CONFIGURED_IMAGE_PIXELS}"
        )

    # Try pyvips first (10x faster when available)
    if VIPS_AVAILABLE and optimize_image_vips is not None:
        try:
            vips_kwargs: dict[str, Any] = {
                "max_width": max_w,
                "max_height": max_h,
                "quality": 85,
                # Pass the resolved default too: omitting max_pixels would
                # leave the pyvips fast path without the application guard.
                "max_pixels": pixel_budget,
            }
            return optimize_image_vips(
                data,
                **vips_kwargs,
            )
        except ImagePixelLimitError:
            raise
        except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — pyvips failure falls back to Pillow (reviewed TD-27-04)
            logger.warning("pyvips failed, falling back to Pillow: %s", exc)

    # Pillow fallback
    try:
        return _optimize_image_pillow(
            data,
            max_width=max_w,
            max_height=max_h,
            max_pixels=pixel_budget,
        )
    except ImagePixelLimitError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Invalid image data") from exc
