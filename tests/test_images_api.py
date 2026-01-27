from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings

# async_client base_url is http://testserver/api/v1
# Routes are relative to the path if no leading slash is used.
# The route for image proxy is /api/v1/img/{path}
IMG_PATH = "img"


@pytest.mark.asyncio
async def test_proxy_image_disabled(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", False):
        response = await async_client.get(f"{IMG_PATH}/test.jpg")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_proxy_image_success(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", True):
        with patch("app.api.images._get_storage_backend"):
            with patch(
                "app.api.images.get_transformed_image", new_callable=AsyncMock
            ) as mock_transform:
                mock_transform.return_value = (b"fake_image_data", "image/jpeg")

                response = await async_client.get(f"{IMG_PATH}/test.jpg?w=100")
                assert response.status_code == 200
                assert response.content == b"fake_image_data"
                assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_proxy_image_not_found(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", True):
        with patch("app.api.images._get_storage_backend"):
            with patch(
                "app.api.images.get_transformed_image", new_callable=AsyncMock
            ) as mock_transform:
                mock_transform.side_effect = ValueError("Not found")

                response = await async_client.get(f"{IMG_PATH}/nonexistent.jpg")
                assert response.status_code == 404


@pytest.mark.asyncio
async def test_proxy_image_internal_error(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", True):
        with patch("app.api.images._get_storage_backend"):
            with patch(
                "app.api.images.get_transformed_image", new_callable=AsyncMock
            ) as mock_transform:
                mock_transform.side_effect = Exception("Unexpected error")

                response = await async_client.get(f"{IMG_PATH}/error.jpg")
                assert response.status_code == 500


@pytest.mark.asyncio
async def test_proxy_image_format_selection(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", True):
        with patch("app.api.images._get_storage_backend"):
            with patch(
                "app.api.images.get_transformed_image", new_callable=AsyncMock
            ) as mock_transform:
                mock_transform.return_value = (b"data", "image/webp")

                # Test WebP preference
                await async_client.get(
                    f"{IMG_PATH}/test.jpg",
                    headers={"Accept": "image/webp,image/apng,*/*"},
                )
                assert mock_transform.called
                kwargs = mock_transform.call_args.kwargs
                assert kwargs["format_preference"] == "webp"

                # Test AVIF preference
                await async_client.get(
                    f"{IMG_PATH}/test.jpg",
                    headers={"Accept": "image/avif,image/webp,*/*"},
                )
                kwargs = mock_transform.call_args.kwargs
                assert kwargs["format_preference"] == "avif"


@pytest.mark.asyncio
async def test_proxy_image_width_snapping(async_client: AsyncClient):
    with patch.object(settings, "image_proxy_enabled", True):
        with patch.object(settings, "image_proxy_allowed_widths", [100, 200, 400]):
            with patch("app.api.images._get_storage_backend"):
                with patch(
                    "app.api.images.get_transformed_image", new_callable=AsyncMock
                ) as mock_transform:
                    mock_transform.return_value = (b"data", "image/jpeg")

                    await async_client.get(f"{IMG_PATH}/test.jpg?w=150")
                    assert mock_transform.called
                    kwargs = mock_transform.call_args.kwargs
                    assert kwargs["width"] in [100, 200]

                    await async_client.get(f"{IMG_PATH}/test.jpg?w=380")
                    kwargs = mock_transform.call_args.kwargs
                    assert kwargs["width"] == 400
