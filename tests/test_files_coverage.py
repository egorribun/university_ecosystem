from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.utils.files import (
    _get_storage_backend,
    _looks_like_polyglot,
    delete_static_file,
    save_attachment,
)


def test_get_storage_backend_reload() -> None:
    # Forces _get_storage_backend signature mismatch and reload flow
    with (
        patch("app.utils.files.storage_backend", None),
        patch("app.utils.files._default_storage_backend", None),
        patch("app.utils.files._storage_backend_snapshot", "old-signature"),
        patch(
            "app.utils.files._storage_backend_signature", return_value="new-signature"
        ),
        patch("app.utils.files.get_storage_backend") as mock_get_backend,
    ):
        mock_get_backend.return_value = MagicMock()
        backend = _get_storage_backend()
        assert backend is not None
        mock_get_backend.assert_called_once()


def test_looks_like_polyglot_scenarios() -> None:
    # 1. PDF containing <script
    assert (
        _looks_like_polyglot(b"pdf data <script>alert(1)</script>", "application/pdf")
        is True
    )
    # 2. SVG without <svg root in first 4096 bytes
    assert _looks_like_polyglot(b"invalid svg header", "image/svg+xml") is True
    # 3. SVG with dangerous patterns
    assert (
        _looks_like_polyglot(b"<svg> <script>alert(1)</script> </svg>", "image/svg+xml")
        is True
    )
    assert (
        _looks_like_polyglot(b"<svg> <image onerror=alert(1)> </svg>", "image/svg+xml")
        is True
    )
    assert (
        _looks_like_polyglot(
            b"<svg> <foreignobject>html</foreignobject> </svg>", "image/svg+xml"
        )
        is True
    )
    # 4. Any other type containing <script and <!doctype html
    assert (
        _looks_like_polyglot(
            b"<!doctype html><html><script>alert(1)</script>", "text/plain"
        )
        is True
    )
    # 5. Safe non-polyglot text
    assert _looks_like_polyglot(b"ordinary file content", "text/plain") is False


@pytest.mark.asyncio
async def test_save_attachment_invalid_limit() -> None:
    headers = {"content-type": "image/png"}
    # Using 1-byte file to not trigger too large limit block
    upload = UploadFile(filename="test.png", file=io.BytesIO(b"d"), headers=headers)
    # Forces TypeError/ValueError in limit conversion
    with patch("app.utils.files.settings") as mock_settings:
        mock_settings.event_file_max_size_bytes = "invalid-limit"
        mock_settings.event_file_allowed_mime_types_set = {"image/png"}
        mock_settings.event_file_allowed_extensions_set = {"png"}
        mock_settings.storage_backend = "local"
        mock_settings.static_dir_path = Path("C:\\dummy_static_dir")
        mock_settings.storage_static_base_url = "http://localhost/"

        # Will raise 415 because detected mime is empty, which triggers quarantine
        with pytest.raises(HTTPException) as exc_info:
            await save_attachment(
                upload,
                subdir="test",
                prefix="prefix",
                max_size_bytes="invalid-max-size-bytes",
                return_meta=True,
            )
        assert exc_info.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_unsupported_mime() -> None:
    headers = {"content-type": "text/plain"}
    upload = UploadFile(filename="test.txt", file=io.BytesIO(b"data"), headers=headers)

    # Target line 376: declared type not allowed
    with pytest.raises(HTTPException) as exc_info:
        await save_attachment(
            upload,
            subdir="test",
            prefix="prefix",
            allowed_mime_types={"image/png"},
            allowed_extensions={"png"},
        )
    assert exc_info.value.status_code == 415


@pytest.mark.asyncio
async def test_save_attachment_quarantine_conditions() -> None:
    # 1. Unknown / empty detected type
    headers = {"content-type": "image/png"}
    upload_empty = UploadFile(filename="test", file=io.BytesIO(b""), headers=headers)
    with (
        patch("app.utils.files.detect_mime_type", return_value=""),
        patch("app.utils.files._quarantine_payload") as mock_quarantine,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await save_attachment(
                upload_empty,
                subdir="test",
                prefix="prefix",
                allowed_mime_types={"image/png"},
                allowed_extensions={"png"},
            )
        assert exc_info.value.status_code == 415
        mock_quarantine.assert_called_once()

    # 2. Blocked declared MIME (declared_type not in allowed_types)
    headers_js = {"content-type": "application/javascript"}
    upload_blocked_decl = UploadFile(
        filename="test.png", file=io.BytesIO(b"png data"), headers=headers_js
    )
    with pytest.raises(HTTPException) as exc_info:
        await save_attachment(
            upload_blocked_decl,
            subdir="test",
            prefix="prefix",
            allowed_mime_types={"image/png"},
            allowed_extensions={"png"},
        )
    assert exc_info.value.status_code == 415

    # 3. Content Type Mismatch (declared_type != detected_type)
    headers_jpeg = {"content-type": "image/jpeg"}
    upload_mismatch = UploadFile(
        filename="test.png", file=io.BytesIO(b"png data"), headers=headers_jpeg
    )
    with (
        patch("app.utils.files.detect_mime_type", return_value="image/png"),
        patch("app.utils.files._quarantine_payload") as mock_quarantine_3,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await save_attachment(
                upload_mismatch,
                subdir="test",
                prefix="prefix",
                allowed_mime_types={"image/png", "image/jpeg"},
                allowed_extensions={"png", "jpg"},
            )
        assert exc_info.value.status_code == 415
        mock_quarantine_3.assert_called_once()


@pytest.mark.asyncio
async def test_save_attachment_blocked_extension() -> None:
    headers = {"content-type": "image/png"}
    # PNG data so that detected_type is image/png (which maps to detected_ext_without_dot = "png")
    # But allowed_extensions only has "bin", blocking it!
    png_header = b"\x89PNG\r\n\x1a\n"
    upload = UploadFile(
        filename="test.png", file=io.BytesIO(png_header), headers=headers
    )
    with (
        patch("app.utils.files.detect_mime_type", return_value="image/png"),
        patch("app.utils.files._quarantine_payload") as mock_quarantine,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await save_attachment(
                upload,
                subdir="test",
                prefix="prefix",
                allowed_mime_types={"image/png"},
                allowed_extensions={"bin"},
            )
        assert exc_info.value.status_code == 415
        mock_quarantine.assert_called_once()


@pytest.mark.asyncio
async def test_delete_static_file_scenarios() -> None:
    # 1. Invalid URL scheme or missing path
    with patch("app.utils.files.settings") as mock_settings:
        mock_settings.storage_backend = "local"
        mock_settings.static_dir_path = Path("C:\\dummy_static_dir")
        mock_settings.storage_static_base_url = "http://localhost/"

        # Non-matching URL
        await delete_static_file("http://external-domain.com/avatar.png")

        # Empty URL
        await delete_static_file("")
