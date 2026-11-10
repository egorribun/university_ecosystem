"""Exercise public image requests against real provider path resolution."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import images
from app.core.config import settings
from app.core.static import is_private_static_path
from app.services.storage import S3Storage, StaticFSStorage

_PRIVATE_ALIASES = (
    "quarantine/news_images/rejected.bin",
    "%252fquarantine/news_images/rejected.bin",
    "%25252fquarantine/news_images/rejected.bin",
    "%2525252fquarantine/news_images/rejected.bin",
    "%252f./quarantine/news_images/rejected.bin",
    "%2520quarantine/news_images/rejected.bin",
    "%2509quarantine/news_images/rejected.bin",
    "static/quarantine/news_images/rejected.bin",
    "%252fstatic/quarantine/news_images/rejected.bin",
    "static/%2520quarantine/news_images/rejected.bin",
    "static/%2520%252fquarantine/news_images/rejected.bin",
    "static/%252fquarantine/news_images/rejected.bin",
    "%255cquarantine/news_images/rejected.bin",
    "quarantine%255cnews_images%255crejected.bin",
)


@pytest.fixture
async def image_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(settings, "image_proxy_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    app = FastAPI()
    app.include_router(images.router, prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://image.test"
    ) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", _PRIVATE_ALIASES)
async def test_filesystem_quarantine_alias_is_blocked_before_cache_or_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    alias: str,
) -> None:
    synthetic = b"synthetic rejected upload"
    target = tmp_path / "quarantine/news_images/rejected.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(synthetic)
    storage = StaticFSStorage(tmp_path)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    cache_factory = AsyncMock(return_value=cache)
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)

    response = await image_client.get(f"/api/v1/img/{alias}")

    assert response.status_code == 404
    assert synthetic not in response.content
    assert "public" not in response.headers.get("cache-control", "")
    cache_factory.assert_not_awaited()
    assert target.read_bytes() == synthetic


@pytest.mark.asyncio
@pytest.mark.parametrize("base_url", ["/media", "/media/assets", ""])
@pytest.mark.parametrize(
    "private_prefix", ["quarantine", "chat_uploads", "event_files"]
)
async def test_filesystem_custom_prefix_cannot_hide_private_storage_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    base_url: str,
    private_prefix: str,
) -> None:
    target = tmp_path / private_prefix / "synthetic.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic private payload")
    storage = StaticFSStorage(tmp_path, base_url=base_url)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    cache_factory = AsyncMock(return_value=cache)
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)

    prefix = base_url.lstrip("/")
    response = await image_client.get(
        f"/api/v1/img/{prefix}/%2520{private_prefix}/synthetic.bin"
    )

    assert response.status_code == 404
    assert b"synthetic private payload" not in response.content
    cache_factory.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["s3", "minio"])
@pytest.mark.parametrize("alias", _PRIVATE_ALIASES)
async def test_object_storage_quarantine_alias_never_reaches_provider(
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    provider: str,
    alias: str,
) -> None:
    client = AsyncMock()
    storage = S3Storage(
        bucket="synthetic",
        endpoint_url="https://minio.invalid" if provider == "minio" else None,
        client=client,
    )
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    cache_factory = AsyncMock(return_value=cache)
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)

    response = await image_client.get(f"/api/v1/img/{alias}")

    assert response.status_code == 404
    client.get_object.assert_not_awaited()
    client.head_object.assert_not_awaited()
    cache_factory.assert_not_awaited()


@pytest.mark.parametrize(
    "path",
    [
        "%2fquarantine/rejected.bin",
        "%252fquarantine/rejected.bin",
        "%25252fquarantine/rejected.bin",
        "%2fstatic/quarantine/rejected.bin",
        "%5cquarantine/rejected.bin",
        "quarantine%255cfile.bin",
    ],
)
def test_static_classifier_normalizes_separators_after_decoding(path: str) -> None:
    assert is_private_static_path(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "alias"),
    [
        ("/static", "avatars/public.bin"),
        ("/static", "%252favatars/public.bin"),
        ("/static", "static/avatars/public.bin"),
        ("/static", "static/%2520avatars/public.bin"),
        ("/media", "media/avatars/public.bin"),
        ("", "avatars/public.bin"),
    ],
)
async def test_filesystem_public_alias_uses_resolved_key_for_cache_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    base_url: str,
    alias: str,
) -> None:
    target = tmp_path / "avatars/public.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic public media")
    storage = StaticFSStorage(tmp_path, base_url=base_url)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
    )

    response = await image_client.get(f"/api/v1/img/{alias}")

    assert response.status_code == 200
    assert response.content == b"synthetic public media"
    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["chat_uploads", "event_files"])
@pytest.mark.parametrize("base_url", ["/static", "/media", ""])
async def test_filesystem_space_fallback_cannot_read_private_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    prefix: str,
    base_url: str,
) -> None:
    target = tmp_path / prefix / "synthetic.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic private attachment")
    storage = StaticFSStorage(tmp_path, base_url=base_url)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    cache_factory = AsyncMock(return_value=cache)
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)
    alias = f"{base_url.lstrip('/')}/{prefix.replace('_', '%20')}/synthetic.bin"

    response = await image_client.get(f"/api/v1/img/{alias}")

    assert response.status_code == 404
    assert b"synthetic private attachment" not in response.content
    cache_factory.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    [
        "avatars/%2500invalid.bin",
        "%252e%252e/quarantine/synthetic.bin",
        "C:%255cfile",
        "avatars%255cpublic.bin",
    ],
)
async def test_filesystem_invalid_image_alias_is_rejected_before_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
    alias: str,
) -> None:
    storage = StaticFSStorage(tmp_path)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache_factory = AsyncMock()
    monkeypatch.setattr("app.deps.cache.get_cache_client", cache_factory)

    response = await image_client.get(f"/api/v1/img/{alias}")

    assert response.status_code == 404
    cache_factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_filesystem_public_space_fallback_remains_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
) -> None:
    target = tmp_path / "story_covers/public_image.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic public fallback")
    storage = StaticFSStorage(tmp_path)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
    )

    response = await image_client.get(
        "/api/v1/img/static/story%20covers/public%20image.bin"
    )

    assert response.status_code == 200
    assert response.content == b"synthetic public fallback"
    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"


@pytest.mark.asyncio
async def test_filesystem_validation_preserves_original_read_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_client: httpx.AsyncClient,
) -> None:
    expected = tmp_path / "static/avatars/public.bin"
    other = tmp_path / "avatars/public.bin"
    expected.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    expected.write_bytes(b"original prefixed object")
    other.write_bytes(b"wrong double-stripped object")
    storage = StaticFSStorage(tmp_path)
    monkeypatch.setattr(images, "_get_storage_backend", lambda: storage)
    cache = AsyncMock()
    cache.get.return_value = None
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
    )

    response = await image_client.get("/api/v1/img/static/static/avatars/public.bin")

    assert response.status_code == 200
    assert response.content == b"original prefixed object"
