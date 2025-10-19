import asyncio
import io
import re

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.core.config import settings
from app.localization import translate
from app.utils import files


def test_normalize_filename_prefix_basic():
    assert files.normalize_filename_prefix("My Avatar 1") == "my-avatar-1"


def test_normalize_filename_prefix_compacts_symbols():
    value = files.normalize_filename_prefix("***Weird__Prefix   ---+++!!!")
    assert value == "weird__prefix"
    assert not re.search(r"\s", value)


@pytest.mark.asyncio
async def test_save_image_offloads_io(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(buffer, format="PNG")
    buffer.seek(0)
    upload = UploadFile(
        filename="avatar.png",
        file=buffer,
        headers=Headers({"content-type": "image/png"}),
    )

    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_to_thread(func, /, *args, **kwargs):  # type: ignore[override]
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(files, "asyncio", asyncio)
    monkeypatch.setattr(files.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    url = await files.save_image(upload, "avatars", "Profile Pic")

    assert url.startswith("/static/avatars/")
    stored = tmp_path / "avatars"
    assert stored.exists()
    assert any(stored.iterdir())
    assert any(func is files._ensure_dir for func, _, _ in calls)
    assert any(func.__name__ == "write_bytes" for func, _, _ in calls)


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

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "image_max_width", 512)
    monkeypatch.setattr(settings, "image_max_height", 512)

    url = await files.save_image(upload, "avatars", "Large Pic")
    rel_path = url.removeprefix("/static/")
    stored_path = settings.static_dir_path / rel_path

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

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "image_max_width", 512)
    monkeypatch.setattr(settings, "image_max_height", 512)

    url = await files.save_image(upload, "avatars", "Transparent Pic")
    rel_path = url.removeprefix("/static/")
    stored_path = settings.static_dir_path / rel_path

    assert stored_path.suffix == ".png"
    with Image.open(stored_path) as saved:
        assert saved.format == "PNG"
        assert saved.mode == "RGBA"
        assert saved.width <= 300
        assert saved.height <= 200
        assert "exif" not in saved.info
