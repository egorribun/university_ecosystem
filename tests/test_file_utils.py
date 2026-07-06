"""Tests for file utility module.

Coverage targets:
- normalize_filename_prefix: slugification
- _ext_from_mime: extension mapping
- _detect_image_mime: PIL vs raw detection
- detect_mime_type: various payloads
- _quarantine_payload: writing to quarantine
- _normalize_mime_type: cleanup
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils.files import (
    _detect_image_mime,
    _ext_from_mime,
    _looks_like_polyglot,
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
    assert (
        _normalize_mime_type("  application/PDF; charset=utf-8  ") == "application/pdf"
    )
    assert _normalize_mime_type(None) == ""


# ============================================================
# _quarantine_payload tests
# ============================================================


@pytest.mark.asyncio
async def test_quarantine_payload(tmp_path):
    """Test writing payload to quarantine."""
    data = b"malicious data"

    # We need to mock _get_storage_backend
    mock_backend = AsyncMock()

    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        await _quarantine_payload(
            data, subdir="avatars", prefix="user", reason="malware"
        )

    mock_backend.save_file.assert_called_once()
    args = mock_backend.save_file.call_args[0]
    assert "quarantine/avatars/user_malware" in args[0]
    assert args[1] == data


def test_detect_image_mime_webp_svg():
    """Verify _detect_image_mime handles webp and svg signatures."""
    webp_data = b"RIFF\x00\x00\x00\x00WEBP\x00\x00\x00"
    assert _detect_image_mime(webp_data) == "image/webp"

    svg_data = b"<svg width='100'></svg>"
    assert _detect_image_mime(svg_data) == "image/svg+xml"


def test_detect_mime_type_svg_fallback():
    """Verify SVG detection fallback when libmagic is not initialized."""
    svg_data = b"<svg width='100'></svg>"
    with patch("app.utils.files._magic_mime_detector", None):
        assert detect_mime_type(svg_data) == "image/svg+xml"


def test_detect_mime_type_libmagic_decoding():
    """Test detect_mime_type with libmagic returning bytes, string, and new init."""
    import app.utils.files as files_module

    mock_magic = MagicMock()

    # Bytes return
    mock_magic.from_buffer.return_value = b"image/png"
    with patch("app.utils.files._magic_mime_detector", mock_magic):
        assert detect_mime_type(b"dummy") == "image/png"

    # String return
    mock_magic.from_buffer.return_value = "image/png"
    with patch("app.utils.files._magic_mime_detector", mock_magic):
        assert detect_mime_type(b"dummy") == "image/png"

    # Initialization fallback mock
    mock_magic_import = MagicMock()
    mock_magic_import.Magic.return_value = mock_magic
    with (
        patch(
            "app.utils.files._magic_mime_detector", files_module._MAGIC_NOT_INITIALIZED
        ),
        patch.dict("sys.modules", {"magic": mock_magic_import}),
    ):
        assert detect_mime_type(b"dummy") == "image/png"


def test_looks_like_polyglot_svg_no_svg_tag():
    """Verify _looks_like_polyglot identifies invalid SVG content."""
    assert _looks_like_polyglot(b"no svg tag here", "image/svg+xml") is True


@pytest.mark.asyncio
async def test_quarantine_payload_error():
    """Verify _quarantine_payload handles and logs save_file failures."""
    mock_backend = AsyncMock()
    mock_backend.save_file.side_effect = OSError("Disk full")

    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        # Should catch and log error without raising
        await _quarantine_payload(b"data", subdir="dir", prefix="pre", reason="rea")


@pytest.mark.asyncio
async def test_save_image_invalid_declared():
    """Verify save_image rejects unsupported declared content types."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_image

    upload = UploadFile(
        filename="test.txt",
        file=io.BytesIO(b""),
        headers={"content-type": "text/plain"},
    )
    with pytest.raises(HTTPException) as exc:
        await save_image(upload, "dir", "prefix")
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_image_invalid_detected():
    """Verify save_image rejects unsupported detected content types."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_image

    upload = UploadFile(
        filename="test.jpg",
        file=io.BytesIO(b"not-an-image"),
        headers={"content-type": "image/jpeg"},
    )
    with pytest.raises(HTTPException) as exc:
        await save_image(upload, "dir", "prefix")
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_image_type_mismatch():
    """Verify save_image rejects mismatched declared/detected content types."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_image

    png_data = b"\x89PNG\r\n\x1a\n"
    upload = UploadFile(
        filename="test.jpg",
        file=io.BytesIO(png_data),
        headers={"content-type": "image/jpeg"},
    )
    with pytest.raises(HTTPException) as exc:
        await save_image(upload, "dir", "prefix")
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_image_polyglot():
    """Verify save_image rejects polyglot image uploads."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_image

    svg_data = b"<svg><script>alert(1)</script></svg>"
    upload = UploadFile(
        filename="test.svg",
        file=io.BytesIO(svg_data),
        headers={"content-type": "image/svg+xml"},
    )
    with pytest.raises(HTTPException) as exc:
        await save_image(upload, "dir", "prefix")
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_image_optimization_error():
    """Verify save_image handles image optimization exceptions."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_image

    jpeg_data = b"\xff\xd8\xff\xee" + b"\x00" * 10
    upload = UploadFile(
        filename="test.jpg",
        file=io.BytesIO(jpeg_data),
        headers={"content-type": "image/jpeg"},
    )

    with patch(
        "app.utils.files.optimize_image", side_effect=ValueError("Corrupt image")
    ):
        with pytest.raises(HTTPException) as exc:
            await save_image(upload, "dir", "prefix")
        assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_invalid_size_limit():
    """Verify save_attachment falls back correctly when limit argument is invalid."""
    import io

    from fastapi import UploadFile

    from app.utils.files import save_attachment

    upload = UploadFile(
        filename="test.pdf",
        file=io.BytesIO(b"%PDF-1.4"),
        headers={"content-type": "application/pdf"},
    )
    mock_backend = AsyncMock()
    mock_backend.save_file.return_value = "http://test/file.pdf"

    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        await save_attachment(
            upload,
            "dir",
            "prefix",
            max_size_bytes="invalid-size",
            allowed_mime_types={"application/pdf"},
            allowed_extensions={"pdf"},
        )


@pytest.mark.asyncio
async def test_save_attachment_invalid_settings_limit():
    """Verify save_attachment handles invalid settings size limits gracefully."""
    import io

    from fastapi import UploadFile

    from app.utils.files import save_attachment, settings

    upload = UploadFile(
        filename="test.pdf",
        file=io.BytesIO(b"%PDF-1.4"),
        headers={"content-type": "application/pdf"},
    )
    mock_backend = AsyncMock()
    mock_backend.save_file.return_value = "http://test/file.pdf"

    with (
        patch("app.utils.files._get_storage_backend", return_value=mock_backend),
        patch.object(settings, "event_file_max_size_bytes", "invalid-config"),
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await save_attachment(upload, "dir", "prefix")


@pytest.mark.asyncio
async def test_save_attachment_unknown_detected_mime():
    """Verify save_attachment rejects files with unknown/empty detected MIME type."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_attachment

    upload = UploadFile(
        filename="test.bin", file=io.BytesIO(b""), headers={"content-type": ""}
    )
    mock_backend = AsyncMock()
    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        with pytest.raises(HTTPException) as exc:
            await save_attachment(upload, "dir", "prefix")
        assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_blocked_declared_mime():
    """Verify save_attachment rejects blocked declared MIME types."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_attachment

    upload = UploadFile(
        filename="test.pdf",
        file=io.BytesIO(b"%PDF-1.4"),
        headers={"content-type": "text/html"},
    )
    mock_backend = AsyncMock()
    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        with pytest.raises(HTTPException) as exc:
            await save_attachment(
                upload, "dir", "prefix", allowed_mime_types={"application/pdf"}
            )
        assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_blocked_extension():
    """Verify save_attachment rejects files with blocked extensions."""
    import io

    from fastapi import HTTPException, UploadFile

    from app.utils.files import save_attachment

    upload = UploadFile(
        filename="test.exe",
        file=io.BytesIO(b"%PDF-1.4"),
        headers={"content-type": "application/pdf"},
    )
    mock_backend = AsyncMock()
    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        with pytest.raises(HTTPException) as exc:
            await save_attachment(upload, "dir", "prefix", allowed_extensions={".pdf"})
        assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_fallback_extension():
    """Verify save_attachment extracts fallback extension from mime mapping when empty."""
    import io

    from fastapi import UploadFile

    from app.utils.files import save_attachment

    upload = UploadFile(
        filename="test",
        file=io.BytesIO(b"%PDF-1.4"),
        headers={"content-type": "application/pdf"},
    )
    mock_backend = AsyncMock()
    mock_backend.save_file.return_value = "http://test/file"
    with patch("app.utils.files._get_storage_backend", return_value=mock_backend):
        res = await save_attachment(
            upload,
            "dir",
            "prefix",
            allowed_extensions={"pdf"},
            allowed_mime_types={"application/pdf"},
        )
        assert res == "http://test/file"
