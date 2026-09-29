"""Cached image bytes must not outlive their source object's availability."""

from unittest.mock import AsyncMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.image_proxy import _CACHE_TTL, _cache_encode, get_transformed_image
from app.services.storage import StorageBackend


@pytest.mark.asyncio
async def test_cached_image_requires_existing_source_object() -> None:
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"cached", "image/webp")
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = True

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        assert await get_transformed_image(
            backend, "avatars/current.png", width=200, format_preference="webp"
        ) == (b"cached", "image/webp")

    backend.exists.assert_awaited_once_with("/avatars/current.png")
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_image_deleted_from_source_fails_closed_and_evicts() -> None:
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"stale", "image/webp")
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = False

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        with pytest.raises(ValueError, match="Could not load image"):
            await get_transformed_image(
                backend, "avatars/deleted.png", width=200, format_preference="webp"
            )

    backend.exists.assert_awaited_once_with("/avatars/deleted.png")
    backend.read_file.assert_not_awaited()
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_image_access_error_cannot_serve_stale_bytes() -> None:
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"stale", "image/webp")
    backend = AsyncMock(spec=StorageBackend)
    error = ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
    backend.exists.side_effect = error

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        with pytest.raises(ClientError) as exc_info:
            await get_transformed_image(
                backend, "avatars/private.png", width=200, format_preference="webp"
            )

    assert exc_info.value is error
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_image_stale_eviction_failure_still_fails_closed() -> None:
    redis = AsyncMock()
    redis.get.return_value = _cache_encode(b"stale", "image/webp")
    redis.delete.side_effect = ConnectionError("Redis unavailable")
    backend = AsyncMock(spec=StorageBackend)
    backend.exists.return_value = False

    with patch("app.deps.cache.get_cache_client", return_value=redis):
        with pytest.raises(ValueError, match="Could not load image"):
            await get_transformed_image(
                backend, "avatars/deleted.png", width=200, format_preference="webp"
            )

    backend.read_file.assert_not_awaited()
    redis.delete.assert_awaited_once()


def test_transformed_image_cache_ttl_bounded_to_one_day() -> None:
    assert _CACHE_TTL == 24 * 60 * 60
