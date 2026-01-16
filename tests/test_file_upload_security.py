import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.utils.files import _looks_like_polyglot, detect_mime_type, save_attachment

# Mock settings for testing
settings.event_file_allowed_mime_types = "image/jpeg,image/png,application/pdf"
settings.event_file_allowed_extensions = ".jpg,.png,.pdf"


@pytest.mark.asyncio
async def test_detect_mime_type_fallback():
    # Test fallback detection without libmagic

    # JPEG
    assert detect_mime_type(b"\xff\xd8\xff\xe0") == "image/jpeg"

    # PNG
    assert detect_mime_type(b"\x89PNG\r\n\x1a\n") == "image/png"

    # PDF
    assert detect_mime_type(b"%PDF-1.4") == "application/pdf"

    # Unknown (e.g. text)
    assert detect_mime_type(b"Just some text") is None


@pytest.mark.asyncio
async def test_polyglot_detection():
    # PDF with script
    pdf_with_script = b"%PDF-1.4\n<script>alert(1)</script>"
    assert _looks_like_polyglot(pdf_with_script, "application/pdf") is True

    # SVG with script
    svg_with_script = b"<svg><script>alert(1)</script></svg>"
    # detect_mime_type will return image/svg+xml
    assert _looks_like_polyglot(svg_with_script, "image/svg+xml") is True

    # Clean PDF
    assert _looks_like_polyglot(b"%PDF-1.4\nContent", "application/pdf") is False


@pytest.mark.asyncio
async def test_save_attachment_mime_mismatch(monkeypatch):
    # Mock storage backend to avoid actual file I/O
    async def mock_save(*args, **kwargs):
        return "http://test/file.jpg"

    monkeypatch.setattr("app.services.storage.StaticFSStorage.save_file", mock_save)

    # Prepare UploadFile with MISMATCHED content type
    content = b"\x89PNG\r\n\x1a\n"  # Real PNG
    headers = {"content-type": "image/jpeg"}
    file = UploadFile(filename="test.jpg", file=io.BytesIO(content), headers=headers)

    # Should raise 415 mismatch
    with pytest.raises(HTTPException) as exc:
        await save_attachment(file, "test", "prefix")
    assert exc.value.status_code == 415
    # The actual detail might be a translation key or string depending on mock
    # Check if 'mismatch' or 'unsupported_type' key is in usage.
    # The code uses 'errors.files.content_type_mismatch'


@pytest.mark.asyncio
async def test_save_attachment_unknown_type(monkeypatch):
    # Unknown type (Text)
    content = b"Simple text file"
    headers = {"content-type": "text/plain"}
    file = UploadFile(filename="test.txt", file=io.BytesIO(content), headers=headers)

    # Should raise 415 because text/plain is not in allowed types AND not detected
    with pytest.raises(HTTPException) as exc:
        await save_attachment(file, "test", "prefix")
    assert exc.value.status_code == 415
