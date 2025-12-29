"""Tests for image_proxy service.

Coverage targets:
- _sanitize_path_input: path traversal detection
- _validate_path_within_base: base directory validation
- _guess_mime: mime type guessing
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.image_proxy import (
    _guess_mime,
    _sanitize_path_input,
    _validate_path_within_base,
)


# ============================================================
# _sanitize_path_input tests
# ============================================================


def test_sanitize_path_input_valid():
    """Test valid path passes through."""
    result = _sanitize_path_input("/static/avatars/user.jpg")
    assert result == "/static/avatars/user.jpg"


def test_sanitize_path_input_simple_filename():
    """Test simple filename passes."""
    result = _sanitize_path_input("image.png")
    assert result == "image.png"


def test_sanitize_path_input_path_traversal():
    """Test path traversal is blocked."""
    with pytest.raises(ValueError, match="Path traversal detected"):
        _sanitize_path_input("../../../etc/passwd")


def test_sanitize_path_input_path_traversal_middle():
    """Test path traversal in middle of path is blocked."""
    with pytest.raises(ValueError, match="Path traversal detected"):
        _sanitize_path_input("/static/../../../etc/passwd")


def test_sanitize_path_input_windows_absolute():
    """Test Windows absolute path is blocked."""
    with pytest.raises(ValueError, match="Windows absolute path"):
        _sanitize_path_input("C:\\Windows\\System32\\config")


def test_sanitize_path_input_null_byte():
    """Test null byte is blocked."""
    with pytest.raises(ValueError, match="Null byte"):
        _sanitize_path_input("/static/image.jpg\x00.php")


def test_sanitize_path_input_encoded_traversal():
    """Test with no direct traversal (encoded handled elsewhere)."""
    # This test ensures only literal .. is blocked
    result = _sanitize_path_input("/static/folder_name/image.jpg")
    assert result == "/static/folder_name/image.jpg"


# ============================================================
# _validate_path_within_base tests
# ============================================================


def test_validate_path_within_base_valid(tmp_path):
    """Test valid path within base."""
    # Create a test file
    test_file = tmp_path / "images" / "test.jpg"
    test_file.parent.mkdir(parents=True)
    test_file.touch()

    result = _validate_path_within_base(tmp_path, Path("images/test.jpg"))
    assert str(result).startswith(str(tmp_path))


def test_validate_path_within_base_traversal():
    """Test path traversal is blocked."""
    base = Path("/var/www/static")

    # Even though we sanitize earlier, this is the secondary defense
    with pytest.raises(ValueError, match="Path traversal attempt"):
        _validate_path_within_base(base, Path("../../etc/passwd"))


def test_validate_path_within_base_absolute_escape():
    """Test absolute path that escapes base is blocked."""
    base = Path("/var/www/static")

    with pytest.raises(ValueError, match="Path traversal attempt"):
        _validate_path_within_base(base, Path("/etc/passwd"))


# ============================================================
# _guess_mime tests
# ============================================================


def test_guess_mime_jpeg():
    """Test JPEG mime type."""
    result = _guess_mime("/path/to/image.jpg")
    assert result == "image/jpeg"


def test_guess_mime_png():
    """Test PNG mime type."""
    result = _guess_mime("/path/to/image.png")
    assert result == "image/png"


def test_guess_mime_webp():
    """Test WebP mime type."""
    result = _guess_mime("/path/to/image.webp")
    assert result == "image/webp"


def test_guess_mime_unknown():
    """Test unknown extension returns default."""
    result = _guess_mime("/path/to/file.xyz123")
    assert result == "application/octet-stream"


def test_guess_mime_no_extension():
    """Test file without extension."""
    result = _guess_mime("/path/to/file")
    assert result == "application/octet-stream"


def test_guess_mime_gif():
    """Test GIF mime type."""
    result = _guess_mime("animation.gif")
    assert result == "image/gif"


def test_guess_mime_svg():
    """Test SVG mime type."""
    result = _guess_mime("icon.svg")
    assert result == "image/svg+xml"
