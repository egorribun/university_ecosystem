"""Closure tests for image proxy cache and width-selection branches."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.api.images import proxy_image
from app.core.config import settings


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/img/test.jpg",
            "headers": headers or [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.asyncio
async def test_proxy_image_uses_requested_width_when_buckets_are_empty():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch.object(settings, "image_proxy_allowed_widths", []),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"data", "image/jpeg")),
        ) as transform,
    ):
        response = await proxy_image(_request(), "test.jpg", w=123, accept=None)

    assert response.status_code == 200
    assert transform.await_args.kwargs["width"] == 123
    assert transform.await_args.kwargs["format_preference"] == "original"


@pytest.mark.asyncio
async def test_proxy_image_returns_not_modified_for_matching_etag():
    data = b"cached-image"
    etag = f'"{hashlib.sha256(data).hexdigest()[:16]}"'

    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(data, "image/jpeg")),
        ),
    ):
        response = await proxy_image(
            _request([(b"if-none-match", etag.encode())]),
            "test.jpg",
            w=None,
            accept="",
        )

    assert response.status_code == 304
    assert response.headers["etag"] == etag


@pytest.mark.asyncio
async def test_proxy_image_marks_user_content_private():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"user-image", "image/jpeg")),
        ),
    ):
        response = await proxy_image(_request(), "avatars/user.jpg", w=None, accept="")

    assert response.headers["cache-control"] == "private, max-age=86400"
    assert response.headers["x-image-proxy-cache"] == "MISS"
