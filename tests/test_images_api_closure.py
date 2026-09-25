"""Closure tests for image proxy cache and width-selection branches."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.images import proxy_image
from app.core.config import settings
from app.services.storage import S3Storage
from app.utils.images import ImagePixelLimitError


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


@pytest.mark.asyncio
async def test_proxy_image_revalidates_user_content_on_matching_etag() -> None:
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
            "avatars/current.jpg",
            w=None,
            accept=None,
        )

    assert response.status_code == 304
    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"
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

    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"
    assert response.headers["x-image-proxy-cache"] == "MISS"


@pytest.mark.asyncio
async def test_proxy_image_disabled_is_hidden_as_not_found():
    with patch.object(settings, "image_proxy_enabled", False):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(_request(), "hidden.jpg")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_proxy_image_rejects_private_attachment_prefixes():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch("app.api.images.get_transformed_image", new=AsyncMock()) as transform,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(
                _request(), "chat_uploads/chat_x/secret.png", w=None, accept=None
            )
    assert exc_info.value.status_code == 404
    transform.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_image_rejects_overencoded_private_attachment_prefixes():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch("app.api.images.get_transformed_image", new=AsyncMock()) as transform,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(
                _request(),
                "%2563hat_uploads%2Fchat_x%2Fsecret.png",
                w=None,
                accept=None,
            )
    assert exc_info.value.status_code == 404
    transform.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_image_rejects_quarantined_payload_before_storage_read():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch("app.api.images.get_transformed_image", new=AsyncMock()) as transform,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(
                _request(),
                "%2571uarantine%2Fnews_images%2Frejected.bin",
                w=None,
                accept=None,
            )
    assert exc_info.value.status_code == 404
    transform.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "internal/secret.png",
        "static/logo.png",
        "avatars/../internal/secret.png",
        "avatars\\internal\\secret.png",
    ],
)
async def test_s3_image_proxy_reads_only_published_media_prefixes(path: str):
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=AsyncMock())
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=storage),
        patch("app.api.images.get_transformed_image", new=AsyncMock()) as transform,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(_request(), path, w=None, accept=None)

    assert exc_info.value.status_code == 404
    transform.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "avatars/user.png",
        "%2561vatars/user.png",
        "covers/user.png",
        "news_images/story.png",
        "story_covers/story.png",
        "tmp/event_images/event.png",
    ],
)
async def test_s3_image_proxy_serves_published_media_through_private_bucket(path: str):
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=AsyncMock())
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=storage),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"image", "image/png")),
        ) as transform,
    ):
        response = await proxy_image(_request(), path, w=None, accept=None)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"
    assert transform.await_args.args[0] is storage


@pytest.mark.asyncio
async def test_proxy_image_snaps_width_and_prefers_avif_for_static_content():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch.object(settings, "image_proxy_allowed_widths", [100, 200]),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"data", "image/avif")),
        ) as transform,
    ):
        response = await proxy_image(
            _request(), "static/logo.png", w=160, accept="image/avif,image/webp"
        )

    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-image-proxy-cache"] == "HIT"
    assert transform.await_args.kwargs["width"] == 200
    assert transform.await_args.kwargs["format_preference"] == "avif"


@pytest.mark.asyncio
async def test_proxy_image_prefers_webp_when_avif_is_absent():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"data", "image/webp")),
        ) as transform,
    ):
        await proxy_image(_request(), "static/logo.png", w=None, accept="image/webp")

    assert transform.await_args.kwargs["format_preference"] == "webp"


@pytest.mark.asyncio
async def test_proxy_image_uses_original_for_unknown_accept_format():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(return_value=(b"data", "image/jpeg")),
        ) as transform,
    ):
        await proxy_image(_request(), "static/logo.png", w=None, accept="image/png")

    assert transform.await_args.kwargs["format_preference"] == "original"


@pytest.mark.asyncio
async def test_proxy_image_maps_storage_errors_to_http_errors():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(side_effect=ValueError("missing")),
        ),
    ):
        with pytest.raises(HTTPException) as not_found:
            await proxy_image(_request(), "missing.jpg", w=None, accept=None)

    assert not_found.value.status_code == 404

    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(side_effect=RuntimeError("backend down")),
        ),
    ):
        with pytest.raises(HTTPException) as internal:
            await proxy_image(_request(), "broken.jpg", w=None, accept=None)

    assert internal.value.status_code == 500


@pytest.mark.asyncio
async def test_proxy_image_maps_pixel_budget_to_payload_too_large():
    with (
        patch.object(settings, "image_proxy_enabled", True),
        patch("app.api.images._get_storage_backend", return_value=object()),
        patch(
            "app.api.images.get_transformed_image",
            new=AsyncMock(side_effect=ImagePixelLimitError(10_000, 10_000, 25_000_000)),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(_request(), "oversized.png", w=None, accept=None)

    assert exc_info.value.status_code == 413
