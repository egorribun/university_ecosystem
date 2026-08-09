"""Unit tests for image optimization fallbacks (Pillow vs libvips) and SVG/HTML sanitization.

Covers:
- Pillow resize and re-encode fallback when pyvips is unavailable.
- libvips integration and fallback under exception gates.
- SVG sanitization against XXE/malicious payloads.
- HTML and rich-text sanitization (nh3).
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.utils.images import optimize_image
from app.utils.sanitization import sanitize_html, sanitize_rich_text


def test_optimize_image_pillow_fallback() -> None:
    # 1. Create a dummy image
    img = Image.new("RGB", (100, 100), color="red")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    jpeg_data = buf.getvalue()

    # 2. Run optimize_image (since pyvips is disabled/not installed locally, it runs Pillow)
    optimized_data, content_type = optimize_image(
        jpeg_data, max_width=50, max_height=50
    )

    assert content_type == "image/webp"
    assert len(optimized_data) > 0

    # Verify size was reduced
    opt_img = Image.open(BytesIO(optimized_data))
    assert opt_img.size == (50, 50)


def test_optimize_image_svg_sanitization() -> None:
    # Safe SVG
    safe_svg = b'<svg width="100" height="100"><circle cx="50" cy="50" r="40" /></svg>'
    optimized_data, content_type = optimize_image(
        safe_svg, content_type="image/svg+xml"
    )
    assert content_type == "image/svg+xml"
    assert optimized_data == safe_svg

    # Malicious SVG with XXE payload
    malicious_svg = b"""<?xml version="1.0" standalone="no"?>
    <!DOCTYPE svg [
      <!ELEMENT svg ANY >
      <!ENTITY xxe SYSTEM "file:///etc/passwd" >
    ]>
    <svg width="100" height="100">
      <text x="0" y="20">&xxe;</text>
    </svg>"""

    with pytest.raises(ValueError, match="Invalid or malicious SVG data"):
        optimize_image(malicious_svg, content_type="image/svg+xml")


def test_optimize_image_vips_routing_and_fallback() -> None:
    # Create a dummy image
    img = Image.new("RGB", (10, 10), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()

    # Case 1: Route to VIPS when VIPS_AVAILABLE is True
    mock_vips_opt = MagicMock(return_value=(b"vips_optimized_webp_bytes", "image/webp"))
    # ``test_images_v2`` reloads ``app.utils.images`` while this module keeps
    # the function imported at collection time. Patch that function's actual
    # globals so the test remains correct regardless of module reload order.
    with patch.dict(
        optimize_image.__globals__,
        {"VIPS_AVAILABLE": True, "optimize_image_vips": mock_vips_opt},
    ):
        optimized_data, content_type = optimize_image(
            png_data, max_width=5, max_height=5
        )
        assert optimized_data == b"vips_optimized_webp_bytes"
        assert content_type == "image/webp"
        mock_vips_opt.assert_called_once_with(
            png_data, max_width=5, max_height=5, quality=85
        )

    # Case 2: VIPS fails with OSError -> Fallback to Pillow
    mock_vips_fail = MagicMock(side_effect=OSError("libvips error"))
    with patch.dict(
        optimize_image.__globals__,
        {"VIPS_AVAILABLE": True, "optimize_image_vips": mock_vips_fail},
    ):
        optimized_data, content_type = optimize_image(
            png_data, max_width=5, max_height=5
        )
        assert content_type == "image/webp"
        assert optimized_data != b"vips_optimized_webp_bytes"

        # Verify it fallback and processed via Pillow
        opt_img = Image.open(BytesIO(optimized_data))
        assert opt_img.size == (5, 5)


def test_html_sanitization_xss_vectors() -> None:
    # 1. Simple tag stripping (allow_basic_tags = False)
    input_str = "<script>alert(1)</script><p>Hello <b>world</b></p>"
    assert sanitize_html(input_str, allow_basic_tags=False) == "Hello world"

    # 2. Allow basic tags (allow_basic_tags = True)
    assert sanitize_html(input_str, allow_basic_tags=True) == "Hello <b>world</b>"

    # 3. Rich text sanitization with allowed anchors & XSS stripping
    rich_input = (
        "<p>Text with <a href='https://example.com' onclick='evil()'>link</a> "
        "<a href='javascript:alert(1)'>invalid scheme</a></p>"
    )
    sanitized_rich = sanitize_rich_text(rich_input)
    assert (
        '<a href="https://example.com" rel="noopener noreferrer">link</a>'
        in sanitized_rich
    )
    assert "onclick" not in sanitized_rich
    assert "javascript:" not in sanitized_rich
