"""Focused branch coverage for upload validation and storage selection."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

import app.utils.files as files_module
from app.utils.files import detect_mime_type, save_attachment, save_image


def test_storage_backend_fast_path_returns_existing_backend(monkeypatch):
    current = object()
    monkeypatch.setattr(files_module, "storage_backend", current)
    monkeypatch.setattr(files_module, "_default_storage_backend", object())

    assert files_module._get_storage_backend() is current


def test_detect_mime_type_uses_module_level_magic_fallback(monkeypatch):
    detector = MagicMock()
    detector.from_buffer.side_effect = AttributeError("legacy API")
    magic_module = SimpleNamespace(from_buffer=lambda _data, mime: "image/png")
    monkeypatch.setattr(files_module, "_magic_mime_detector", detector)
    monkeypatch.setattr(files_module, "_magic_module", magic_module)

    assert detect_mime_type(b"payload") == "image/png"


def test_detect_mime_type_uses_signature_when_magic_returns_unknown(monkeypatch):
    detector = MagicMock()
    detector.from_buffer.return_value = None
    monkeypatch.setattr(files_module, "_magic_mime_detector", detector)
    monkeypatch.setattr(files_module, "_magic_module", None)

    assert detect_mime_type(b"%PDF-1.7 payload") == "application/pdf"


@pytest.mark.asyncio
async def test_save_image_success_writes_optimized_payload():
    upload = UploadFile(
        filename="avatar.png",
        file=io.BytesIO(b"raw"),
        headers={"content-type": "image/png"},
    )
    backend = AsyncMock()
    backend.save_file.return_value = "/static/avatar.webp"

    with (
        patch.object(files_module, "_read_limited", new=AsyncMock(return_value=b"raw")),
        patch.object(files_module, "_detect_image_mime", return_value="image/png"),
        patch.object(files_module, "_looks_like_polyglot", return_value=False),
        patch.object(
            files_module,
            "optimize_image",
            return_value=(b"optimized", "image/webp"),
        ),
        patch.object(files_module, "_get_storage_backend", return_value=backend),
        patch.object(files_module, "_prepare_local_storage", new=AsyncMock()),
    ):
        result = await save_image(upload, "avatars", "user")

    assert result == "/static/avatar.webp"
    backend.save_file.assert_awaited_once()
    assert backend.save_file.await_args.args[0].startswith("avatars/")
    assert backend.save_file.await_args.args[1] == b"optimized"


@pytest.mark.asyncio
async def test_save_image_rejects_polyglot_after_mime_detection():
    upload = UploadFile(
        filename="avatar.png",
        file=io.BytesIO(b"raw"),
        headers={"content-type": "image/png"},
    )

    with (
        patch.object(files_module, "_read_limited", new=AsyncMock(return_value=b"raw")),
        patch.object(files_module, "_detect_image_mime", return_value="image/png"),
        patch.object(files_module, "_looks_like_polyglot", return_value=True),
    ):
        with pytest.raises(HTTPException):
            await save_image(upload, "avatars", "user")


@pytest.mark.asyncio
async def test_save_attachment_rejects_detected_mime_outside_allowlist():
    upload = UploadFile(
        filename="document.pdf",
        file=io.BytesIO(b"payload"),
        headers={"content-type": "application/pdf"},
    )
    quarantine = AsyncMock()

    with (
        patch.object(files_module, "detect_mime_type", return_value="image/png"),
        patch.object(files_module, "_quarantine_payload", new=quarantine),
    ):
        with pytest.raises(HTTPException):
            await save_attachment(
                upload,
                "documents",
                "doc",
                allowed_mime_types={"application/pdf"},
            )

    quarantine.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_attachment_rejects_polyglot_and_returns_metadata_on_success():
    malicious = UploadFile(
        filename="document.pdf",
        file=io.BytesIO(b"payload"),
        headers={"content-type": "application/pdf"},
    )
    quarantine = AsyncMock()
    with (
        patch.object(files_module, "detect_mime_type", return_value="application/pdf"),
        patch.object(files_module, "_looks_like_polyglot", return_value=True),
        patch.object(files_module, "_quarantine_payload", new=quarantine),
    ):
        with pytest.raises(HTTPException):
            await save_attachment(
                malicious,
                "documents",
                "doc",
                allowed_mime_types={"application/pdf"},
            )
    quarantine.assert_awaited_once()

    valid = UploadFile(
        filename="document",
        file=io.BytesIO(b"%PDF-1.7"),
        headers={"content-type": "application/pdf"},
    )
    backend = AsyncMock()
    backend.save_file.return_value = "/static/document"
    with (
        patch.object(files_module, "detect_mime_type", return_value="application/pdf"),
        patch.object(files_module, "_looks_like_polyglot", return_value=False),
        patch.object(files_module, "_ext_from_mime", return_value=""),
        patch.object(files_module, "scan_for_malware", new=AsyncMock()),
        patch.object(files_module, "_get_storage_backend", return_value=backend),
        patch.object(files_module, "_prepare_local_storage", new=AsyncMock()),
    ):
        result = await save_attachment(
            valid,
            "documents",
            "doc",
            allowed_mime_types={"application/pdf"},
            allowed_extensions=set(),
            max_size_bytes=100,
            return_meta=True,
        )

    assert result["url"] == "/static/document"
    assert result["detected_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_save_attachment_accepts_matching_allowed_extension():
    upload = UploadFile(
        filename="document.pdf",
        file=io.BytesIO(b"%PDF-1.7"),
        headers={"content-type": "application/pdf"},
    )
    backend = AsyncMock()
    backend.save_file.return_value = "/static/document.pdf"

    with (
        patch.object(files_module, "detect_mime_type", return_value="application/pdf"),
        patch.object(files_module, "_looks_like_polyglot", return_value=False),
        patch.object(files_module, "scan_for_malware", new=AsyncMock()),
        patch.object(files_module, "_get_storage_backend", return_value=backend),
        patch.object(files_module, "_prepare_local_storage", new=AsyncMock()),
    ):
        result = await save_attachment(
            upload,
            "documents",
            "doc",
            allowed_mime_types={"application/pdf"},
            allowed_extensions={"pdf"},
            max_size_bytes=100,
        )

    assert result == "/static/document.pdf"


@pytest.mark.asyncio
async def test_save_attachment_keeps_mime_extension_without_allowlist():
    upload = UploadFile(
        filename="document.pdf",
        file=io.BytesIO(b"%PDF-1.7"),
        headers={"content-type": "application/pdf"},
    )
    backend = AsyncMock()
    backend.save_file.return_value = "/static/document.pdf"

    with (
        patch.object(files_module, "detect_mime_type", return_value="application/pdf"),
        patch.object(files_module, "_looks_like_polyglot", return_value=False),
        patch.object(files_module, "scan_for_malware", new=AsyncMock()),
        patch.object(files_module, "_get_storage_backend", return_value=backend),
        patch.object(files_module, "_prepare_local_storage", new=AsyncMock()),
    ):
        result = await save_attachment(
            upload,
            "documents",
            "doc",
            allowed_mime_types={"application/pdf"},
            allowed_extensions=set(),
            max_size_bytes=100,
        )

    assert result == "/static/document.pdf"
