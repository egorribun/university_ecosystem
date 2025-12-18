"""Image processing helpers for uploaded files."""

from __future__ import annotations

from io import BytesIO
from typing import cast

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_svg_string
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # Pillow >= 9.1 exposes the resampling enum in PIL.Image
    from PIL.Image import Resampling
except ImportError:  # pragma: no cover - Pillow < 9.1 compatibility
    Resampling = int  # type: ignore[misc,assignment]


def _resolve_resample_filter() -> Resampling:
    """Return the best available high-quality resampling filter."""

    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return cast(Resampling, resampling.LANCZOS)
    lanczos = getattr(Image, "LANCZOS", None)
    if lanczos is None:
        raise AttributeError("Pillow installation does not expose a LANCZOS filter")
    return cast(Resampling, lanczos)


def sanitize_svg(data: bytes) -> bytes:
    """Validate and sanitize SVG data to prevent XXE and other XML-based attacks."""
    try:
        # defusedxml will raise an error if it finds any suspicious XML
        parse_svg_string(data)
        return data
    except (DefusedXmlException, Exception) as exc:
        raise ValueError("Invalid or malicious SVG data") from exc


def optimize_image(
    data: bytes,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
    content_type: str | None = None,
) -> tuple[bytes, str]:
    """Resize and re-encode an image to an optimized WebP or PNG payload.

    The helper ensures the image fits within the configured bounding box, strips
    EXIF metadata, and converts the image to an efficient format.
    """

    # Handle SVG separately
    if content_type == "image/svg+xml" or data.lstrip().startswith(b"<svg"):
        return sanitize_svg(data), "image/svg+xml"

    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size

            max_w = int(max_width or 0)
            max_h = int(max_height or 0)
            if max_w <= 0:
                max_w = width
            if max_h <= 0:
                max_h = height

            if width > max_w or height > max_h:
                resample = _resolve_resample_filter()
                img.thumbnail((max_w, max_h), resample=resample)

            has_alpha = "A" in img.getbands()

            buffer = BytesIO()
            # Prefer WebP for all images if possible, otherwise use PNG for alpha transparency if WebP is not desired
            # But WebP supports alpha, so we can use it for everything.
            img.save(buffer, format="WEBP", method=6, quality=85, lossless=False)
            mime = "image/webp"

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:  # pragma: no cover - runtime guard
        raise ValueError("Invalid image data") from exc

    return buffer.getvalue(), mime
