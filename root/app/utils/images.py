"""Image processing helpers for uploaded files."""

from __future__ import annotations

from io import BytesIO
from typing import cast

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


def optimize_image(
    data: bytes, *, max_width: int | None = None, max_height: int | None = None
) -> tuple[bytes, str]:
    """Resize and re-encode an image to an optimized PNG or WebP payload.

    The helper ensures the image fits within the configured bounding box, strips
    EXIF metadata, and converts the image to an efficient format.
    """

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
            target_mode = "RGBA" if has_alpha else "RGB"
            if img.mode != target_mode:
                img = img.convert(target_mode)

            buffer = BytesIO()
            if has_alpha:
                img.save(buffer, format="PNG", optimize=True)
                mime = "image/png"
            else:
                img.save(buffer, format="WEBP", method=6, quality=85)
                mime = "image/webp"
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:  # pragma: no cover - runtime guard
        raise ValueError("Invalid image data") from exc

    return buffer.getvalue(), mime
