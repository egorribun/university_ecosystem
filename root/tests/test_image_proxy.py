"""Tests for the image proxy service."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.image_proxy import (
    _guess_mime,
    _process_image,
    get_transformed_image,
)

if TYPE_CHECKING:
    from app.services.storage import StorageBackend


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Create a sample PNG image for testing."""
    img = Image.new("RGB", (200, 100), color="red")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def mock_storage_backend():
    """Create a mock storage backend."""
    backend = MagicMock()
    return backend


class TestGuessUnknownMime:
    """Tests for _guess_mime function."""

    def test_guess_jpeg(self):
        assert _guess_mime("image.jpg") == "image/jpeg"
        assert _guess_mime("image.jpeg") == "image/jpeg"

    def test_guess_png(self):
        assert _guess_mime("image.png") == "image/png"

    def test_guess_webp(self):
        assert _guess_mime("image.webp") == "image/webp"

    def test_guess_unknown(self):
        assert _guess_mime("file.xyz") == "application/octet-stream"

    def test_guess_with_path(self):
        assert _guess_mime("/uploads/images/photo.jpg") == "image/jpeg"


class TestProcessImage:
    """Tests for _process_image function."""

    def test_no_transformation_returns_original(self, sample_image_bytes):
        """When format is original and no width, return original format."""
        result_data, mime = _process_image(sample_image_bytes, None, "original")
        assert mime == "image/png"
        assert len(result_data) > 0

    def test_resize_width(self, sample_image_bytes):
        """Resize image to smaller width."""
        result_data, mime = _process_image(sample_image_bytes, 100, "original")
        # Verify the resulting image has correct width
        with Image.open(BytesIO(result_data)) as img:
            assert img.size[0] == 100
            # Height should be proportionally scaled (original 200x100 -> 100x50)
            assert img.size[1] == 50

    def test_no_upscale(self, sample_image_bytes):
        """Width larger than original should not upscale."""
        result_data, mime = _process_image(sample_image_bytes, 400, "original")
        # Original should be kept as-is
        with Image.open(BytesIO(result_data)) as img:
            assert img.size[0] == 200  # Original width unchanged

    def test_webp_conversion(self, sample_image_bytes):
        """Convert to WebP format."""
        result_data, mime = _process_image(sample_image_bytes, None, "webp")
        assert mime == "image/webp"
        with Image.open(BytesIO(result_data)) as img:
            assert img.format == "WEBP"

    def test_webp_with_resize(self, sample_image_bytes):
        """Convert to WebP and resize."""
        result_data, mime = _process_image(sample_image_bytes, 50, "webp")
        assert mime == "image/webp"
        with Image.open(BytesIO(result_data)) as img:
            assert img.format == "WEBP"
            assert img.size[0] == 50


class TestGetTransformedImage:
    """Tests for the main get_transformed_image async function."""

    @pytest.mark.asyncio
    async def test_returns_cached_data(self, sample_image_bytes, mock_storage_backend):
        """Should return cached data if available."""
        with patch("app.services.image_proxy.image_cache") as mock_cache:
            mock_cache.get.return_value = (sample_image_bytes, "image/png")

            result_data, mime = await get_transformed_image(
                mock_storage_backend, "/test/image.png", None, "original"
            )

            assert result_data == sample_image_bytes
            assert mime == "image/png"
            mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_and_caches_on_miss(
        self, sample_image_bytes, mock_storage_backend
    ):
        """Should fetch from backend and cache on cache miss."""
        with (
            patch("app.services.image_proxy.image_cache") as mock_cache,
            patch(
                "app.services.image_proxy._fetch_source_bytes",
                new_callable=AsyncMock,
            ) as mock_fetch,
        ):
            mock_cache.get.return_value = None
            mock_fetch.return_value = sample_image_bytes

            result_data, mime = await get_transformed_image(
                mock_storage_backend, "/test/image.png", None, "original"
            )

            assert mime == "image/png"
            assert len(result_data) > 0

    @pytest.mark.asyncio
    async def test_webp_transformation(self, sample_image_bytes, mock_storage_backend):
        """Should transform to WebP format."""
        with (
            patch("app.services.image_proxy.image_cache") as mock_cache,
            patch(
                "app.services.image_proxy._fetch_source_bytes",
                new_callable=AsyncMock,
            ) as mock_fetch,
        ):
            mock_cache.get.return_value = None
            mock_fetch.return_value = sample_image_bytes

            result_data, mime = await get_transformed_image(
                mock_storage_backend, "/test/image.png", 100, "webp"
            )

            assert mime == "image/webp"
            mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_error_raises_value_error(self, mock_storage_backend):
        """Should raise ValueError when fetch fails."""
        with (
            patch("app.services.image_proxy.image_cache") as mock_cache,
            patch(
                "app.services.image_proxy._fetch_source_bytes",
                new_callable=AsyncMock,
            ) as mock_fetch,
        ):
            mock_cache.get.return_value = None
            mock_fetch.side_effect = IOError("Network error")

            with pytest.raises(ValueError, match="Could not load image"):
                await get_transformed_image(
                    mock_storage_backend, "/test/missing.png", None, "original"
                )

    @pytest.mark.asyncio
    async def test_transformation_error_returns_original(
        self, sample_image_bytes, mock_storage_backend
    ):
        """Should return original on transformation error."""
        with (
            patch("app.services.image_proxy.image_cache") as mock_cache,
            patch(
                "app.services.image_proxy._fetch_source_bytes",
                new_callable=AsyncMock,
            ) as mock_fetch,
            patch(
                "app.services.image_proxy._process_image",
                side_effect=Exception("Processing error"),
            ),
        ):
            mock_cache.get.return_value = None
            mock_fetch.return_value = sample_image_bytes

            result_data, mime = await get_transformed_image(
                mock_storage_backend, "/test/image.jpg", 100, "webp"
            )

            # Should fall back to original
            assert result_data == sample_image_bytes
            assert mime == "image/jpeg"
