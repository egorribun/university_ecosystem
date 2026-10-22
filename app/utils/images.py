"""Image processing helpers for uploaded files.

This module uses pyvips when available (10x faster than Pillow) with
automatic fallback to Pillow for Windows or when pyvips is not installed.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from defusedxml.ElementTree import fromstring as parse_svg_string
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import Resampling

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


_IMAGE_FORMATS_BY_MIME: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}
_MAX_METADATA_SANITIZATION_FRAMES = 10_000


def strip_image_metadata(
    data: bytes, *, content_type: str, max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS
) -> bytes:
    """Re-encode supported raster images without location-bearing metadata.

    The detected format is retained so the caller can keep its MIME type and
    extension consistent. Animated formats retain each frame and its timing;
    EXIF orientation is applied to pixels before metadata is discarded. ICC
    profiles are retained because they affect color interpretation rather than
    identifying a user.
    """
    expected_format = _IMAGE_FORMATS_BY_MIME.get(content_type)
    if expected_format is None:
        raise ValueError("Unsupported image format for metadata sanitization")

    try:
        with Image.open(BytesIO(data)) as source:
            if source.format != expected_format:
                raise ValueError("Detected image format does not match its payload")

            frame_count = int(getattr(source, "n_frames", 1))
            if frame_count < 1 or frame_count > _MAX_METADATA_SANITIZATION_FRAMES:
                raise ValueError("Image frame count exceeds the sanitization limit")
            is_animated = bool(getattr(source, "is_animated", frame_count > 1))

            original_info = dict(source.info)
            frames: list[Image.Image] = []
            durations: list[int | float] = []
            total_pixels = 0

            for frame_index in range(frame_count):
                source.seek(frame_index)
                width, height = source.size
                validate_image_dimensions(width, height, max_pixels=max_pixels)
                total_pixels += width * height
                validate_image_dimensions(total_pixels, 1, max_pixels=max_pixels)

                frame = source.copy()
                # Some decoders, including WebP, finish populating per-frame
                # metadata only when the frame is loaded by ``copy``.
                frame_info = dict(source.info)
                frame = ImageOps.exif_transpose(frame)
                # Pillow's multi-frame writers copy selected ``info`` keys
                # into output chunks. Keep only non-identifying frame state.
                safe_frame_info: dict[str | tuple[int, int], Any] = {}
                if "transparency" in frame_info:
                    safe_frame_info["transparency"] = frame_info["transparency"]
                frame.info = safe_frame_info
                frames.append(frame)

                durations.append(frame_info.get("duration", 0))

            output = BytesIO()
            save_options: dict[str, Any] = {
                "format": expected_format,
                "icc_profile": original_info.get("icc_profile"),
            }

            if expected_format == "JPEG":
                frames[0].save(
                    output,
                    **save_options,
                    quality=95,
                    subsampling=0,
                    exif=b"",
                    xmp=b"",
                )
            elif expected_format == "GIF":
                # GIF transparency and background values are palette indices.
                # Re-encoding decoded frames can create new or local palettes,
                # so carrying source indices forward can make an opaque color
                # transparent (or expose the wrong disposal background).
                gif_frames = [frame.convert("RGBA") for frame in frames]
                for frame in gif_frames:
                    frame.info = {}

                save_options.update(
                    save_all=frame_count > 1,
                    append_images=gif_frames[1:],
                    duration=(durations if frame_count > 1 else durations[0]),
                    # Pillow decodes each frame as the displayed canvas. Use
                    # fresh palette transparency and restore to its background
                    # before each next full-canvas composite.
                    disposal=2,
                    optimize=False,
                )
                if "loop" in original_info:
                    save_options["loop"] = original_info["loop"]
                gif_frames[0].save(output, **save_options)
            elif expected_format == "WEBP":
                save_options.update(
                    save_all=frame_count > 1,
                    append_images=frames[1:],
                    duration=durations,
                    lossless=True,
                    method=6,
                    exif=b"",
                    xmp=b"",
                )
                save_options["loop"] = original_info.get("loop", 0)
                save_options["background"] = original_info.get(
                    "background", (0, 0, 0, 0)
                )
                frames[0].save(output, **save_options)
            else:
                # PNG also covers APNG: Pillow's per-frame controls preserve
                # per-frame durations. Decoded APNG frames are already
                # composited, so source disposal/blend controls would apply
                # those operations twice. Re-encode the visible frames with
                # SOURCE blending and no disposal instead.
                # With a separate default image, APNG timing and frame controls
                # apply only to animation frames (append_images), not IDAT.
                controls_offset = int(bool(original_info.get("default_image")))
                if is_animated:
                    animation_durations = durations[controls_offset:]
                    save_options.update(
                        save_all=True,
                        append_images=frames[1:],
                        duration=animation_durations,
                        disposal=[0] * len(animation_durations),
                        blend=[0] * len(animation_durations),
                    )
                    save_options["loop"] = original_info.get("loop", 0)
                    if "default_image" in original_info:
                        save_options["default_image"] = original_info["default_image"]
                else:
                    save_options["save_all"] = False
                frames[0].save(output, **save_options)

            return output.getvalue()
    except ImagePixelLimitError:
        raise
    except (Image.DecompressionBombError, EOFError, OSError, SyntaxError) as exc:
        raise ValueError("Invalid image data") from exc


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
    # ``0`` is an explicitly invalid policy value, not an instruction to use
    # the default.  Preserve ``None`` as the only sentinel so callers cannot
    # accidentally bypass the lower bound before the guard below runs.
    pixel_budget = int(
        max_pixels if max_pixels is not None else DEFAULT_MAX_IMAGE_PIXELS
    )
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
