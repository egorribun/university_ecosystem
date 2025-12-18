import asyncio
import io
import re

import pytest
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from starlette.datastructures import Headers

from app.core.config import settings
from app.localization import translate
from app.services import file_scanner
from app.services.storage import StaticFSStorage
from app.utils import files


def test_normalize_filename_prefix_basic():
    assert files.normalize_filename_prefix("My Avatar 1") == "my-avatar-1"


def test_normalize_filename_prefix_compacts_symbols():
    value = files.normalize_filename_prefix("***Weird__Prefix   ---+++!!!")
    assert value == "weird__prefix"
    assert not re.search(r"\s", value)


class RecordingStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def save_file(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        self.calls.append(
            (
                "save",
                (relative_path, data),
                {"content_type": content_type, "cache_control": cache_control},
            )
        )
        return f"https://cdn.example/{relative_path}"

    async def delete_file(
        self, file_url: str
    ) -> None:  # pragma: no cover - unused in tests
        self.calls.append(("delete", (file_url,), {}))


@pytest.mark.asyncio
async def test_save_image_uses_storage_backend(monkeypatch):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(buffer, format="PNG")
    buffer.seek(0)
    upload = UploadFile(
        filename="avatar.png",
        file=buffer,
        headers=Headers({"content-type": "image/png"}),
    )

    backend = RecordingStorage()

    async def fake_to_thread(func, /, *args, **kwargs):  # type: ignore[override]
        return func(*args, **kwargs)

    monkeypatch.setattr(files, "asyncio", asyncio)
    monkeypatch.setattr(files.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(files, "storage_backend", backend)

    url = await files.save_image(upload, "avatars", "Profile Pic")

    assert url.startswith("https://cdn.example/avatars/")
    assert backend.calls
    method, (relative_path, data), kwargs = backend.calls[0]
    assert method == "save"
    assert relative_path.startswith("avatars/")
    assert isinstance(data, bytes | bytearray)
    assert kwargs["content_type"] in {"image/webp", "image/png"}


@pytest.mark.parametrize(
    "locale",
    ["ru", "en", "de"],
)
@pytest.mark.asyncio
async def test_save_image_reports_localized_unsupported_type(locale):
    upload = UploadFile(
        filename="avatar.gif",
        file=io.BytesIO(b"GIF89a" + b"\x00" * 10),
        headers=Headers({"content-type": "image/gif"}),
    )

    with pytest.raises(HTTPException) as excinfo:
        await files.save_image(upload, "avatars", "Profile Pic", locale=locale)

    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale=locale
    )


@pytest.mark.asyncio
async def test_save_image_reports_localized_size_limit(monkeypatch):
    payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    upload = UploadFile(
        filename="avatar.png",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "image/png"}),
    )

    monkeypatch.setattr(files, "MAX_IMAGE_SIZE", 1)

    with pytest.raises(HTTPException) as excinfo:
        await files.save_image(upload, "avatars", "Profile Pic", locale="ru")

    assert excinfo.value.detail == translate("errors.files.too_large", locale="ru")


@pytest.mark.asyncio
async def test_save_image_resizes_and_converts_large_images(tmp_path, monkeypatch):
    big = Image.new("RGB", (4000, 2000), color=(255, 0, 0))
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")
    buffer.seek(0)

    upload = UploadFile(
        filename="huge.png",
        file=buffer,
        headers=Headers({"content-type": "image/png"}),
    )

    monkeypatch.setattr(
        files,
        "storage_backend",
        StaticFSStorage(tmp_path, base_url="/static"),
    )
    monkeypatch.setattr(settings, "image_max_width", 512)
    monkeypatch.setattr(settings, "image_max_height", 512)

    url = await files.save_image(upload, "avatars", "Large Pic")
    rel_path = url.removeprefix("/static/")
    stored_path = files.storage_backend.base_dir / rel_path  # type: ignore[attr-defined]

    assert stored_path.suffix == ".webp"
    with Image.open(stored_path) as saved:
        assert saved.format == "WEBP"
        assert saved.width <= 512
        assert saved.height <= 512
        assert "exif" not in saved.info


@pytest.mark.asyncio
async def test_save_image_preserves_transparency_with_png(tmp_path, monkeypatch):
    image = Image.new("RGBA", (300, 200), color=(0, 128, 255, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    upload = UploadFile(
        filename="transparent.png",
        file=buffer,
        headers=Headers({"content-type": "image/png"}),
    )

    monkeypatch.setattr(
        files,
        "storage_backend",
        StaticFSStorage(tmp_path, base_url="/static"),
    )
    monkeypatch.setattr(settings, "image_max_width", 512)
    monkeypatch.setattr(settings, "image_max_height", 512)

    url = await files.save_image(upload, "avatars", "Transparent Pic")
    rel_path = url.removeprefix("/static/")
    stored_path = files.storage_backend.base_dir / rel_path  # type: ignore[attr-defined]

    assert stored_path.suffix == ".webp"
    with Image.open(stored_path) as saved:
        assert saved.format == "WEBP"
        assert saved.mode == "RGBA"
        assert saved.width <= 300
        assert saved.height <= 200
        assert "exif" not in saved.info


@pytest.mark.asyncio
async def test_save_attachment_rejects_mismatched_types(monkeypatch):
    payload = b"%PDF-1.7\n" + b"0" * 10
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    backend = RecordingStorage()

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None, **kwargs
    ) -> None:
        assert scanned == payload
        assert kwargs.get("quarantine_payload") == payload
        assert size_bytes == len(payload)

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)
    monkeypatch.setattr(files, "storage_backend", backend)
    monkeypatch.setattr(files, "_default_storage_backend", backend)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(
        settings,
        "event_file_allowed_mime_types",
        ["text/plain", "application/pdf"],
    )
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt", ".pdf"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    with pytest.raises(HTTPException) as excinfo:
        await files.save_attachment(upload, "event_files", "event_1")

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.content_type_mismatch", locale="en"
    )
    assert backend.calls
    method, (relative_path, data), kwargs = backend.calls[0]
    assert method == "save"
    assert "quarantine" in relative_path
    assert data == payload


@pytest.mark.asyncio
async def test_save_attachment_accepts_matching_declared_type(monkeypatch):
    payload = b"hello world"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    backend = RecordingStorage()

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None, **kwargs
    ) -> None:
        assert scanned == payload
        assert kwargs.get("quarantine_payload") == payload
        assert size_bytes == len(payload)

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)
    monkeypatch.setattr(files, "storage_backend", backend)
    monkeypatch.setattr(files, "_default_storage_backend", backend)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "text/plain")
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    url = await files.save_attachment(upload, "event_files", "event_1")

    assert url.startswith("https://cdn.example/event_files/")
    assert url.endswith(".txt")
    method, (relative_path, data), kwargs = backend.calls[0]
    assert relative_path.endswith(".txt")
    assert kwargs["content_type"] == "text/plain"
    assert data == payload


@pytest.mark.asyncio
async def test_scan_for_malware_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr(settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(settings, "event_file_scanner_backend", "unknown")

    with pytest.raises(HTTPException) as excinfo:
        await files.scan_for_malware(b"payload", locale="en")

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert excinfo.value.detail == translate(
        "errors.files.scanner_unavailable", locale="en"
    )


@pytest.mark.asyncio
async def test_scan_for_malware_handles_scanner_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(settings, "event_file_scanner_backend", "clamd")

    async def fail_scan(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise file_scanner.FileScannerUnavailableError("offline")

    monkeypatch.setattr(file_scanner, "_scan_bytes_with_clamd", fail_scan)

    with pytest.raises(HTTPException) as excinfo:
        await files.scan_for_malware(b"payload", locale="fr")

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert excinfo.value.detail == translate(
        "errors.files.scanner_unavailable", locale="fr"
    )
