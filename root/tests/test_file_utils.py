"""Tests for file utility module.

Coverage targets:
- normalize_filename_prefix: slugification
- _ext_from_mime: extension mapping
- _detect_image_mime: PIL vs raw detection
- detect_mime_type: various payloads
- _quarantine_payload: writing to quarantine
- _normalize_mime_type: cleanup
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.files import (
    _detect_image_mime,
    _ext_from_mime,
    _normalize_mime_type,
    _quarantine_payload,
    detect_mime_type,
    normalize_filename_prefix,
)


# ============================================================
# normalize_filename_prefix tests
# ============================================================


def test_normalize_filename_prefix_simple():
    """Test standard prefix normalization."""
    assert normalize_filename_prefix("Avatar") == "avatar"
    assert normalize_filename_prefix("My-Prefix") == "my-prefix"


def test_normalize_filename_prefix_complex():
    """Test prefix with special characters."""
    assert normalize_filename_prefix("User @ Name!") == "user-name"
    assert normalize_filename_prefix("image.png") == "image.png"
    assert normalize_filename_prefix("  spaces  ") == "spaces"


# ============================================================
# _ext_from_mime tests
# ============================================================


def test_ext_from_mime():
    """Test extension mapping from mime types."""
    # Extensions can vary by system, but .jpg is usually there or .jpe/.jpeg
    ext = _ext_from_mime("image/jpeg")
    assert ext.startswith(".")
    assert len(ext) >= 3


# ============================================================
# _detect_image_mime tests
# ============================================================


def test_detect_image_mime_jpeg():
    """Test detecting JPEG via signature."""
    # Correct signature: FFD8FF
    data = b"\xff\xd8\xff\xee" + b"\x00" * 10
    assert _detect_image_mime(data) == "image/jpeg"


def test_detect_image_mime_png():
    """Test detecting PNG via signature."""
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    assert _detect_image_mime(data) == "image/png"


def test_detect_image_mime_invalid():
    """Test detecting invalid image data."""
    assert _detect_image_mime(b"not an image") is None


# ============================================================
# detect_mime_type tests
# ============================================================


def test_detect_mime_type_empty():
    """Test empty data."""
    assert detect_mime_type(b"") is None


def test_detect_mime_type_pdf():
    """Test detecting PDF via fallback."""
    assert detect_mime_type(b"%PDF-1.4") == "application/pdf"


# ============================================================
# _normalize_mime_type tests
# ============================================================


def test_normalize_mime_type():
    """Test normalizing mime strings."""
    assert _normalize_mime_type("IMAGE/PNG") == "image/png"
    assert _normalize_mime_type("  application/PDF; charset=utf-8  ") == "application/pdf"
    assert _normalize_mime_type(None) == ""


# ============================================================
# _quarantine_payload tests
# ============================================================


@pytest.mark.anyio
async def test_quarantine_payload(tmp_path):
    """Test writing payload to quarantine."""
    data = b"malicious data"

    # We need to mock _get_storage_backend
    mock_backend = AsyncMock()

    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        await _quarantine_payload(
            data,
            subdir="avatars",
            prefix="user",
            reason="malware"
        )

    mock_backend.save_file.assert_called_once()
    args = mock_backend.save_file.call_args[0]
    assert "quarantine/avatars/user_malware" in args[0]
    assert args[1] == data
