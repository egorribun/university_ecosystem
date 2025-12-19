import pytest

from app.utils.images import optimize_image, sanitize_svg


def test_sanitize_svg_valid():
    svg_data = b'<svg xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40"/></svg>'
    result = sanitize_svg(svg_data)
    assert result == svg_data


def test_sanitize_svg_invalid():
    # Attempting XXE or just malformed XML
    malicious_svg = b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg>&xxe;</svg>'
    with pytest.raises(ValueError, match="Invalid or malicious SVG data"):
        sanitize_svg(malicious_svg)


def test_optimize_image_to_webp():
    # Create a small red pixel PNG
    # 89 50 4E 47 ...
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfe\x0dcG\x04\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    optimized, mime = optimize_image(png_data)
    assert mime == "image/webp"
    assert optimized.startswith(b"RIFF")
    assert b"WEBP" in optimized[:12]


def test_optimize_image_svg_passthrough():
    svg_data = b"<svg><circle/></svg>"
    optimized, mime = optimize_image(svg_data, content_type="image/svg+xml")
    assert mime == "image/svg+xml"
    assert optimized == svg_data
