"""Cache invalidation contracts for the remaining image-proxy mutants."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.image_proxy import _cache_encode, get_transformed_image
from app.services.storage import StorageBackend


@pytest.mark.asyncio
async def test_cached_source_path_preserves_leading_non_separator_characters():
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"cached", "image/webp")
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = True

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        assert await get_transformed_image(
            backend, "/XXavatars/current.png", width=200, format_preference="webp"
        ) == (b"cached", "image/webp")

    backend.exists.assert_awaited_once_with("/XXavatars/current.png")
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_cached_source_evicts_the_exact_requested_cache_key():
    path = "avatars/deleted.png"
    expected_key = (
        "image_proxy:" + hashlib.sha256(f"{path}:200:webp".encode()).hexdigest()
    )
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"stale", "image/webp")
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = False

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        with pytest.raises(ValueError, match="Could not load image"):
            await get_transformed_image(
                backend, path, width=200, format_preference="webp"
            )

    redis.delete.assert_awaited_once_with(expected_key)
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", [ConnectionError, TimeoutError, OSError, RuntimeError]
)
async def test_stale_cache_eviction_warning_retains_context_and_original_error(
    error_type,
):
    error = error_type("Redis unavailable")
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"stale", "image/webp")
    redis.delete.side_effect = error
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = False

    with (
        patch("app.deps.cache.get_cache_client", return_value=redis),
        patch("app.services.image_proxy.logger.warning") as warning,
    ):
        with pytest.raises(ValueError, match="Could not load image"):
            await get_transformed_image(
                backend, "avatars/deleted.png", width=200, format_preference="webp"
            )

    warning.assert_called_once_with("Redis stale image eviction failed: %s", error)
    backend.read_file.assert_not_awaited()
