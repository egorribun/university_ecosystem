"""Coverage boost for app/utils/files.py (currently 81%).

Targets uncovered branches:
  - _get_storage_backend: settings-change refresh path (line 49-52)
  - _prepare_local_storage: StaticFSStorage with subdir (lines 67-69)
  - detect_mime_type: PDF fallback (line 183-184), SVG fallback (lines 186-188)
  - save_image: polyglot rejection (line 319-323), optimize_image ValueError (lines 332-340)
  - save_attachment: various quarantine paths and extension-fallback branches
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_upload(
    data: bytes,
    content_type: str = "image/jpeg",
    filename: str = "test.jpg",
) -> UploadFile:
    """Return a minimal UploadFile backed by in-memory bytes."""
    file_obj = io.BytesIO(data)
    upload = MagicMock(spec=UploadFile)
    upload.content_type = content_type
    upload.filename = filename
    upload.read = AsyncMock(return_value=data)
    return upload


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff" + b"\x00" * 100


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# _get_storage_backend — settings refresh path
# ---------------------------------------------------------------------------


class TestGetStorageBackendRefresh:
    def test_refreshes_when_signature_changes(self) -> None:
        """When settings signature changes, a new backend is created."""
        from app.utils import files as files_module

        original_backend = files_module.storage_backend
        original_snapshot = files_module._storage_backend_snapshot

        try:
            # Force a different signature by temporarily patching the function
            new_backend = MagicMock()
            with patch(
                "app.utils.files._storage_backend_signature",
                return_value=("different",),
            ):
                with patch(
                    "app.utils.files.get_storage_backend", return_value=new_backend
                ):
                    # Reset so backend == _default_storage_backend (refresh trigger)
                    files_module._default_storage_backend = files_module.storage_backend
                    result = files_module._get_storage_backend()

            assert result is new_backend
        finally:
            # Restore original state
            files_module.storage_backend = original_backend
            files_module._default_storage_backend = original_backend
            files_module._storage_backend_snapshot = original_snapshot


# ---------------------------------------------------------------------------
# _prepare_local_storage
# ---------------------------------------------------------------------------


class TestPrepareLocalStorage:
    @pytest.mark.asyncio
    async def test_creates_subdir_for_static_fs_backend(self) -> None:
        """For StaticFSStorage with a subdir, creates the sub-path."""
        from app.services.storage import StaticFSStorage
        from app.utils.files import _prepare_local_storage

        backend = MagicMock(spec=StaticFSStorage)
        backend.base_dir = Path("/tmp/static")

        with patch(
            "app.utils.files.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            await _prepare_local_storage(backend, "uploads")

        mock_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_non_fs_backend(self) -> None:
        """For non-StaticFSStorage backend, no directory is created."""
        from app.utils.files import _prepare_local_storage

        backend = MagicMock()  # Not a StaticFSStorage

        with patch("app.utils.files.asyncio.to_thread") as mock_thread:
            await _prepare_local_storage(backend, "uploads")

        mock_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_subdir_uses_base_dir(self) -> None:
        """When subdir is empty, base_dir is used directly."""
        from app.services.storage import StaticFSStorage
        from app.utils.files import _prepare_local_storage

        backend = MagicMock(spec=StaticFSStorage)
        backend.base_dir = Path("/tmp/static")

        with patch(
            "app.utils.files.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            await _prepare_local_storage(backend, "")

        mock_thread.assert_awaited_once()


# ---------------------------------------------------------------------------
# detect_mime_type — fallback paths
# ---------------------------------------------------------------------------


class TestDetectMimeTypeFallbacks:
    def test_returns_none_for_empty_bytes(self) -> None:
        from app.utils.files import detect_mime_type

        assert detect_mime_type(b"") is None

    def test_returns_pdf_for_pdf_header(self) -> None:
        from app.utils.files import detect_mime_type

        # When libmagic is unavailable (or returns nothing), should return pdf
        with patch("app.utils.files._magic_mime_detector", None):
            result = detect_mime_type(b"%PDF-1.4 content here")

        assert result == "application/pdf"

    def test_returns_svg_via_tag_fallback(self) -> None:
        from app.utils.files import detect_mime_type

        svg_data = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='50'/></svg>"
        with patch("app.utils.files._magic_mime_detector", None):
            result = detect_mime_type(svg_data)

        assert result == "image/svg+xml"

    def test_bytes_result_from_magic_decoded(self) -> None:
        """When libmagic returns bytes instead of str, decode gracefully."""
        from app.utils.files import detect_mime_type

        mock_detector = MagicMock()
        mock_detector.from_buffer.return_value = b"image/jpeg"

        with patch("app.utils.files._magic_mime_detector", mock_detector):
            result = detect_mime_type(_jpeg_bytes())

        assert result == "image/jpeg"


# ---------------------------------------------------------------------------
# _looks_like_polyglot — SVG patterns
# ---------------------------------------------------------------------------


class TestLooksLikePolyglot:
    def test_svg_without_svg_tag_is_polyglot(self) -> None:
        """SVG content-type but no <svg> tag → polyglot."""
        from app.utils.files import _looks_like_polyglot

        assert _looks_like_polyglot(b"some random data", "image/svg+xml")

    def test_svg_with_script_tag_is_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"<svg><script>alert(1)</script></svg>"
        assert _looks_like_polyglot(data, "image/svg+xml")

    def test_svg_with_javascript_uri_is_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"<svg><a href='javascript:alert(1)'>x</a></svg>"
        assert _looks_like_polyglot(data, "image/svg+xml")

    def test_svg_with_foreign_object_is_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"<svg><foreignObject><div>evil</div></foreignObject></svg>"
        assert _looks_like_polyglot(data, "image/svg+xml")

    def test_clean_svg_is_not_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='50'/></svg>"
        assert not _looks_like_polyglot(data, "image/svg+xml")

    def test_pdf_with_script_is_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"%PDF-1.4 <script>alert(1)</script>"
        assert _looks_like_polyglot(data, "application/pdf")

    def test_pdf_without_script_is_not_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"%PDF-1.4 clean content"
        assert not _looks_like_polyglot(data, "application/pdf")

    def test_html_with_script_and_doctype_is_polyglot(self) -> None:
        from app.utils.files import _looks_like_polyglot

        data = b"<!doctype html><html><script>alert(1)</script></html>"
        assert _looks_like_polyglot(data, "image/jpeg")


# ---------------------------------------------------------------------------
# save_image — error paths
# ---------------------------------------------------------------------------


class TestSaveImageErrors:
    @pytest.mark.asyncio
    async def test_polyglot_image_rejected(self) -> None:
        """save_image rejects files that look like polyglots."""
        from fastapi import HTTPException

        from app.utils.files import save_image

        # PNG bytes but content-type says PNG — add script to trigger polyglot
        data = _png_bytes() + b"<script>alert(1)</script>"
        upload = _make_upload(data, content_type="image/png", filename="evil.png")

        with (
            patch("app.utils.files._detect_image_mime", return_value="image/png"),
            patch("app.utils.files._looks_like_polyglot", return_value=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_image(upload, "test", "profile")

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_optimize_image_valueerror_becomes_415(self) -> None:
        """When optimize_image raises ValueError, save_image returns 415."""
        from fastapi import HTTPException

        from app.utils.files import save_image

        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/jpeg", filename="test.jpg")

        with (
            patch("app.utils.files._detect_image_mime", return_value="image/jpeg"),
            patch("app.utils.files._looks_like_polyglot", return_value=False),
            patch(
                "app.utils.files.asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=ValueError("Cannot process image"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_image(upload, "test", "profile")

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_unsupported_declared_type_rejected(self) -> None:
        """save_image rejects when declared content_type is not in ALLOWED_IMAGE_TYPES."""
        from fastapi import HTTPException

        from app.utils.files import save_image

        upload = _make_upload(b"data", content_type="text/plain", filename="test.txt")

        with pytest.raises(HTTPException) as exc_info:
            await save_image(upload, "test", "file")

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_detected_type_mismatch_rejected(self) -> None:
        """save_image rejects when detected type differs from declared type."""
        from fastapi import HTTPException

        from app.utils.files import save_image

        # Declare PNG but actual bytes are JPEG
        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/png", filename="test.png")

        with pytest.raises(HTTPException) as exc_info:
            await save_image(upload, "test", "pic")

        assert exc_info.value.status_code == 415


# ---------------------------------------------------------------------------
# save_attachment — quarantine and extension fallback paths
# ---------------------------------------------------------------------------


class TestSaveAttachmentPaths:
    @pytest.mark.asyncio
    async def test_blocked_mime_quarantines_and_raises(self) -> None:
        """When detected MIME is not in allowed_types, quarantine and raise 415."""
        from fastapi import HTTPException

        from app.utils.files import save_attachment

        pdf_data = b"%PDF-1.4 content"
        upload = _make_upload(
            pdf_data, content_type="application/pdf", filename="doc.pdf"
        )

        with (
            patch("app.utils.files.detect_mime_type", return_value="application/pdf"),
            patch("app.utils.files._quarantine_payload", new_callable=AsyncMock),
            patch("app.utils.files.scan_for_malware", new_callable=AsyncMock),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_attachment(
                    upload,
                    "docs",
                    "attachment",
                    allowed_mime_types={"image/jpeg"},  # PDF not allowed
                )

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_extension_not_in_allowed_quarantines(self) -> None:
        """When file extension is not in allowed_extensions, quarantine and raise."""
        from fastapi import HTTPException

        from app.utils.files import save_attachment

        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/jpeg", filename="photo.jpg")

        with (
            patch("app.utils.files.detect_mime_type", return_value="image/jpeg"),
            patch("app.utils.files._quarantine_payload", new_callable=AsyncMock),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_attachment(
                    upload,
                    "pics",
                    "img",
                    allowed_mime_types={"image/jpeg"},
                    allowed_extensions={"png"},  # jpg not allowed
                )

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_unknown_mime_quarantines_and_raises(self) -> None:
        """When MIME cannot be detected, file is quarantined and 415 returned."""
        from fastapi import HTTPException

        from app.utils.files import save_attachment

        upload = _make_upload(b"\x00\x00\x00", content_type="", filename="unknown.bin")

        with (
            patch("app.utils.files.detect_mime_type", return_value=None),
            patch("app.utils.files._quarantine_payload", new_callable=AsyncMock),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_attachment(upload, "files", "attachment")

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_content_type_mismatch_quarantines(self) -> None:
        """Declared type ≠ detected type → quarantine and 415."""
        from fastapi import HTTPException

        from app.utils.files import save_attachment

        # Declared as PNG but detected as JPEG
        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/png", filename="trick.png")

        with (
            patch("app.utils.files.detect_mime_type", return_value="image/jpeg"),
            patch("app.utils.files._quarantine_payload", new_callable=AsyncMock),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await save_attachment(
                    upload,
                    "pics",
                    "img",
                    allowed_mime_types={"image/jpeg", "image/png"},
                )

        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_successful_save_returns_url(self) -> None:
        """Happy path: returns URL string."""
        from app.utils.files import save_attachment

        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/jpeg", filename="photo.jpg")

        mock_backend = AsyncMock()
        mock_backend.save_file = AsyncMock(return_value="http://cdn/photo.jpg")

        with (
            patch("app.utils.files.detect_mime_type", return_value="image/jpeg"),
            patch("app.utils.files._looks_like_polyglot", return_value=False),
            patch("app.utils.files.scan_for_malware", new_callable=AsyncMock),
            patch("app.utils.files._get_storage_backend", return_value=mock_backend),
            patch("app.utils.files._prepare_local_storage", new_callable=AsyncMock),
        ):
            result = await save_attachment(
                upload,
                "pics",
                "photo",
                allowed_mime_types={"image/jpeg"},
                allowed_extensions={"jpg"},
            )

        assert result == "http://cdn/photo.jpg"

    @pytest.mark.asyncio
    async def test_return_meta_includes_size_and_type(self) -> None:
        """When return_meta=True, returns a dict with url, content_type, size, etc."""
        from app.utils.files import save_attachment

        jpeg = _jpeg_bytes()
        upload = _make_upload(jpeg, content_type="image/jpeg", filename="photo.jpg")

        mock_backend = AsyncMock()
        mock_backend.save_file = AsyncMock(return_value="http://cdn/photo.jpg")

        with (
            patch("app.utils.files.detect_mime_type", return_value="image/jpeg"),
            patch("app.utils.files._looks_like_polyglot", return_value=False),
            patch("app.utils.files.scan_for_malware", new_callable=AsyncMock),
            patch("app.utils.files._get_storage_backend", return_value=mock_backend),
            patch("app.utils.files._prepare_local_storage", new_callable=AsyncMock),
        ):
            result = await save_attachment(
                upload,
                "pics",
                "photo",
                allowed_mime_types={"image/jpeg"},
                allowed_extensions={"jpg"},
                return_meta=True,
            )

        assert isinstance(result, dict)
        assert result["url"] == "http://cdn/photo.jpg"
        assert "size" in result
        assert "content_type" in result

    @pytest.mark.asyncio
    async def test_max_size_bytes_override(self) -> None:
        """max_size_bytes param overrides settings.event_file_max_size_bytes."""
        from fastapi import HTTPException

        from app.utils.files import save_attachment

        # File larger than our custom limit
        large_data = b"\xff\xd8\xff" + b"x" * 200
        upload = MagicMock(spec=UploadFile)
        upload.content_type = "image/jpeg"
        upload.filename = "large.jpg"
        # read() returns data that's 1 byte over the limit
        upload.read = AsyncMock(return_value=large_data)

        with pytest.raises(HTTPException) as exc_info:
            await save_attachment(
                upload,
                "pics",
                "img",
                max_size_bytes=100,  # only allow 100 bytes
                allowed_mime_types={"image/jpeg"},
            )

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_quarantine_ioerror_logged_not_raised(self) -> None:
        """_quarantine_payload swallows OSError (logs warning instead of crashing)."""
        from app.utils.files import _quarantine_payload

        mock_backend = AsyncMock()
        mock_backend.save_file = AsyncMock(side_effect=OSError("disk full"))

        with (
            patch("app.utils.files._get_storage_backend", return_value=mock_backend),
            patch("app.utils.files._prepare_local_storage", new_callable=AsyncMock),
        ):
            # Should NOT raise
            await _quarantine_payload(
                b"evil data",
                subdir="uploads",
                prefix="test",
                reason="blocked",
            )
