"""Space aliases must resolve consistently without reviving deleted cached bytes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from botocore.exceptions import ClientError
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from PIL import Image

from app.api import images
from app.core.config import settings
from app.services.image_proxy import _cache_encode
from app.services.storage import S3Storage, StaticFSStorage, StorageBackend


def _png(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), color=color).save(output, "PNG")
    return output.getvalue()


class _S3Objects:
    """Only the remote transport is replaced; S3Storage resolves all keys."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads: list[str] = []

    async def put_object(self, **kwargs: Any) -> None:
        self.objects[kwargs["Key"]] = kwargs["Body"]

    async def delete_object(self, **kwargs: Any) -> None:
        self.objects.pop(kwargs["Key"], None)

    async def head_object(self, **kwargs: Any) -> None:
        key = kwargs["Key"]
        self.reads.append(key)
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    async def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        self.reads.append(key)
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body = AsyncMock()
        body.read.return_value = self.objects[key]
        body.__aenter__.return_value = body
        return {"Body": body}


@pytest.fixture(params=["static", "s3", "minio"])
def storage_case(
    request: pytest.FixtureRequest, tmp_path: Path
) -> tuple[StorageBackend, str, _S3Objects | None]:
    if request.param == "static":
        return (
            StaticFSStorage(tmp_path, base_url="/media/assets"),
            "media/assets/",
            None,
        )
    remote = _S3Objects()
    storage = S3Storage(
        bucket="synthetic",
        endpoint_url="https://minio.invalid" if request.param == "minio" else None,
        client=remote,
    )
    return storage, "", remote


@pytest.fixture
async def image_client(
    monkeypatch: pytest.MonkeyPatch,
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(settings, "image_proxy_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage_case[0])
    async with FakeRedis() as cache:
        monkeypatch.setattr(
            "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
        )
        app = FastAPI()
        app.include_router(images.router, prefix="/api/v1")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://image.test"
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_transformed_space_fallback_survives_warm_cache(
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
    image_client: httpx.AsyncClient,
) -> None:
    storage, prefix, _ = storage_case
    await storage.save_file("avatars/public_image.png", _png((0, 0, 255)))
    url = f"/api/v1/img/{prefix}avatars/public%20image.png?w=100"
    responses = [await image_client.get(url) for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert len({response.content for response in responses}) == 1
    assert all(
        response.headers["cache-control"] == "private, no-cache, must-revalidate"
        for response in responses
    )


@pytest.mark.asyncio
async def test_deleted_original_cache_cannot_override_existing_fallback(
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
    image_client: httpx.AsyncClient,
) -> None:
    storage, prefix, _ = storage_case
    original = await storage.save_file("avatars/public image.png", _png((255, 0, 0)))
    await storage.save_file("avatars/public_image.png", _png((0, 0, 255)))
    url = f"/api/v1/img/{prefix}avatars/public%20image.png?w=100"
    cold = await image_client.get(url)
    assert cold.status_code == 200
    await storage.delete_file(original)
    warm = await image_client.get(url)
    assert warm.status_code == 200
    assert warm.content != cold.content
    with Image.open(BytesIO(warm.content)) as image:
        assert image.getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.asyncio
async def test_deleted_fallback_cannot_be_served_from_warm_cache(
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
    image_client: httpx.AsyncClient,
) -> None:
    storage, prefix, _ = storage_case
    fallback = await storage.save_file("avatars/public_image.png", _png((0, 0, 255)))
    url = f"/api/v1/img/{prefix}avatars/public%20image.png?w=100"
    cold = await image_client.get(url)
    assert cold.status_code == 200
    await storage.delete_file(fallback)
    assert (await image_client.get(url)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "private", ["chat%20uploads", "event%20files", "%2520quarantine"]
)
async def test_private_space_alias_cannot_reach_even_populated_cache(
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
    image_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    private: str,
) -> None:
    _, prefix, remote = storage_case
    cache_factory = AsyncMock()
    cache_factory.return_value.get.return_value = _cache_encode(
        b"private synthetic bytes", "image/png"
    )
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)
    response = await image_client.get(
        f"/api/v1/img/{prefix}{private}/private.png?w=100"
    )
    assert response.status_code == 404
    assert b"private synthetic bytes" not in response.content
    cache_factory.assert_not_awaited()
    if remote:
        assert remote.reads == []


@pytest.mark.asyncio
async def test_deleted_fallback_cache_cannot_be_revived_by_new_original(
    storage_case: tuple[StorageBackend, str, _S3Objects | None],
    image_client: httpx.AsyncClient,
) -> None:
    storage, prefix, _ = storage_case
    fallback = await storage.save_file("avatars/public_image.png", _png((0, 0, 255)))
    url = f"/api/v1/img/{prefix}avatars/public%20image.png?w=100"
    cold = await image_client.get(url)
    assert cold.status_code == 200
    await storage.delete_file(fallback)
    await storage.save_file("avatars/public image.png", _png((255, 0, 0)))
    warm = await image_client.get(url)
    assert warm.status_code == 200
    assert warm.content != cold.content
    with Image.open(BytesIO(warm.content)) as image:
        assert image.getpixel((0, 0)) == (255, 0, 0)
