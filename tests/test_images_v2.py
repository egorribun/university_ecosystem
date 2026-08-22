import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.utils.images as img_mod


def test_sanitize_svg_valid():
    svg_data = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<circle cx="50" cy="50" r="40"/></svg>'
    )
    result = img_mod.sanitize_svg(svg_data)
    assert result == svg_data


def test_sanitize_svg_invalid():
    # Attempting XXE or just malformed XML
    malicious_svg = (
        b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg>&xxe;</svg>'
    )
    with pytest.raises(ValueError, match="Invalid or malicious SVG data"):
        img_mod.sanitize_svg(malicious_svg)


def test_optimize_image_to_webp():
    # Create a small red pixel PNG
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfe\x0dcG\x04\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    optimized, mime = img_mod.optimize_image(png_data)
    assert mime == "image/webp"
    assert optimized.startswith(b"RIFF")
    assert b"WEBP" in optimized[:12]


def test_optimize_image_svg_passthrough():
    svg_data = b"<svg><circle/></svg>"
    optimized, mime = img_mod.optimize_image(svg_data, content_type="image/svg+xml")
    assert mime == "image/svg+xml"
    assert optimized == svg_data


def test_images_vips_import_error():
    """Test importing app.utils.images when images_vips is not available."""
    # Force reload to test import error exception block
    if "app.utils.images" in sys.modules:
        del sys.modules["app.utils.images"]
    if "app.utils.images_vips" in sys.modules:
        del sys.modules["app.utils.images_vips"]

    with patch.dict("sys.modules", {"app.utils.images_vips": None}):
        import app.utils.images as test_img_mod

        assert test_img_mod.VIPS_AVAILABLE is False
        assert test_img_mod.optimize_image_vips is None

    # Restore default state by reloading again without mock
    if "app.utils.images" in sys.modules:
        del sys.modules["app.utils.images"]
    if "app.utils.images_vips" in sys.modules:
        del sys.modules["app.utils.images_vips"]

    import app.utils.images as restored_img_mod

    # Update global reference for other tests in this file
    global img_mod
    img_mod = restored_img_mod


def test_resolve_resample_filter_fallbacks():
    """Test fallback logic in _resolve_resample_filter when Image.Resampling is missing."""
    from PIL import Image

    from app.utils.images import _resolve_resample_filter

    with (
        patch.object(Image, "Resampling", None, create=True),
        patch.object(Image, "LANCZOS", 999, create=True),
    ):
        assert _resolve_resample_filter() == 999

    with (
        patch.object(Image, "Resampling", None, create=True),
        patch.object(Image, "LANCZOS", None, create=True),
    ):
        with pytest.raises(
            AttributeError, match="Pillow installation does not expose a LANCZOS filter"
        ):
            _resolve_resample_filter()


def test_resolve_resample_filter_reports_missing_legacy_attribute():
    """A Pillow build without either resampling API fails with our contract error."""
    from app.utils.images import _resolve_resample_filter

    with patch.object(img_mod, "Image", SimpleNamespace(Resampling=None)):
        with pytest.raises(
            AttributeError, match="Pillow installation does not expose a LANCZOS filter"
        ):
            _resolve_resample_filter()


def test_optimize_image_pillow_resize_and_bounds():
    """Test thumbnail resizing in Pillow and zero/negative bounds handling."""
    from io import BytesIO

    from PIL import Image as PILImage

    # Force VIPS_AVAILABLE=False for this test
    old_vips = img_mod.VIPS_AVAILABLE
    img_mod.VIPS_AVAILABLE = False
    try:
        # 10x10 red square
        img = PILImage.new("RGB", (10, 10), color="red")
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        # Small bounds -> forces resizing branch
        _, mime = img_mod.optimize_image(png_data, max_width=5, max_height=5)
        assert mime == "image/webp"

        # Zero bounds -> sets to 1920 default
        _, mime_defaults = img_mod.optimize_image(png_data, max_width=0, max_height=0)
        assert mime_defaults == "image/webp"
    finally:
        img_mod.VIPS_AVAILABLE = old_vips


def test_optimize_image_vips_failure_fallback():
    """Test fallback to Pillow if VIPS optimization raises an exception."""
    from io import BytesIO

    from PIL import Image as PILImage

    img = PILImage.new("RGB", (2, 2), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()

    mock_vips_opt = MagicMock(side_effect=Exception("Simulated VIPS failure"))
    with (
        patch("app.utils.images.VIPS_AVAILABLE", True),
        patch("app.utils.images.optimize_image_vips", mock_vips_opt),
    ):
        _, mime = img_mod.optimize_image(png_data, max_width=5, max_height=5)
        assert mime == "image/webp"
        mock_vips_opt.assert_called_once()


def test_optimize_image_invalid_data():
    """Test optimize_image raises ValueError on invalid image bytes."""
    with patch("app.utils.images.VIPS_AVAILABLE", False):
        with pytest.raises(ValueError, match="Invalid image data"):
            img_mod.optimize_image(b"not-an-image-payload")


def test_optimize_image_negative_bounds():
    from io import BytesIO

    from PIL import Image as PILImage

    img = PILImage.new("RGB", (2, 2), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()
    _, mime = img_mod.optimize_image(png_data, max_width=-10, max_height=-5)
    assert mime == "image/webp"


def test_optimize_image_with_exif_orientation():
    from io import BytesIO

    from PIL import Image as PILImage

    old_vips = img_mod.VIPS_AVAILABLE
    img_mod.VIPS_AVAILABLE = False
    try:
        img = PILImage.new("RGB", (10, 10), color="blue")
        exif = img.getexif()
        exif[274] = 3
        buf = BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        jpg_data = buf.getvalue()
        _optimized, mime = img_mod.optimize_image(jpg_data)
        assert mime == "image/webp"
    finally:
        img_mod.VIPS_AVAILABLE = old_vips


def test_optimize_image_exif_transpose_none_coverage():
    from io import BytesIO
    from unittest.mock import patch

    from PIL import Image as PILImage

    old_vips = img_mod.VIPS_AVAILABLE
    img_mod.VIPS_AVAILABLE = False
    try:
        img = PILImage.new("RGB", (10, 10), color="blue")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        jpg_data = buf.getvalue()

        with patch("app.utils.images.ImageOps.exif_transpose", return_value=None):
            _optimized, mime = img_mod.optimize_image(jpg_data)
            assert mime == "image/webp"
    finally:
        img_mod.VIPS_AVAILABLE = old_vips
