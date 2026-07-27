"""Focused coverage for image-proxy fallback and defensive branches."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.image_proxy import (
    _fetch_source_bytes,
    _process_image,
    _sanitize_path_input,
)
from app.services.storage import StorageBackend


@pytest.mark.asyncio
async def test_fetch_source_bytes_reraises_missing_file_without_space_fallback():
    backend = AsyncMock(spec=StorageBackend)
    backend.read_file.side_effect = FileNotFoundError("missing")

    with pytest.raises(FileNotFoundError):
        await _fetch_source_bytes(backend, "/static/avatar.png")

    backend.read_file.assert_awaited_once_with("/static/avatar.png")


def test_sanitize_path_input_decodes_multiple_layers():
    assert _sanitize_path_input("%2573tatic%252Fimage.jpg") == "static/image.jpg"


def test_process_image_returns_avif_when_encoding_succeeds():
    image = MagicMock()
    image.size = (1, 1)
    image.format = "PNG"
    image.__enter__.return_value = image

    def save(buffer, *, format, **_kwargs):
        assert format == "AVIF"
        buffer.write(b"avif-data")

    image.save.side_effect = save

    with patch("app.services.image_proxy.Image.open", return_value=image):
        data, mime = _process_image(b"source", None, "avif")

    assert data == b"avif-data"
    assert mime == "image/avif"


def test_image_proxy_cache_and_avif_import_branches():
    msgspec_package = types.ModuleType("msgspec")
    msgpack_module = types.ModuleType("msgspec.msgpack")
    msgpack_module.encode = lambda _payload: b"encoded"
    msgpack_module.decode = lambda _payload: {"d": b"decoded", "m": "image/png"}
    msgspec_package.__path__ = []
    msgspec_package.msgpack = msgpack_module
    module_path = Path(__file__).parents[1] / "app" / "services" / "image_proxy.py"

    with patch.dict(
        sys.modules,
        {
            "msgspec": msgspec_package,
            "msgspec.msgpack": msgpack_module,
            "pillow_avif": None,
        },
    ):
        namespace = runpy.run_path(
            str(module_path), run_name="image_proxy_branch_probe"
        )

    assert namespace["_cache_encode"](b"data", "image/png") == b"encoded"
    assert namespace["_cache_decode"](b"encoded") == (b"decoded", "image/png")
