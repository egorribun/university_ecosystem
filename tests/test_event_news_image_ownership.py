from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.services import content_media
from app.services.content_media import delete_owned_event_image
from app.services.storage import S3Storage, StaticFSStorage


@pytest.mark.asyncio
async def test_local_event_image_deletes_only_matching_generated_key(
    tmp_path, monkeypatch
):
    event_id = uuid4()
    filename = f"event_{event_id}_{'a' * 32}.webp"
    key = f"tmp/event_images/{filename}"
    image = tmp_path / "tmp" / "event_images" / filename
    image.parent.mkdir(parents=True)
    image.write_bytes(b"owned")
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: backend)

    assert await delete_owned_event_image(f"/static/{key}", event_id=event_id)
    assert not image.exists()


@pytest.mark.asyncio
async def test_local_foreign_and_legacy_image_keys_are_retained(tmp_path, monkeypatch):
    event_id = uuid4()
    foreign_id = uuid4()
    keys = [
        f"tmp/event_images/event_{foreign_id}_{'b' * 32}.png",
        "tmp/event_images/legacy.png",
        "news_images/shared-news-image.png",
    ]
    paths: list[Path] = []
    for key in keys:
        path = tmp_path.joinpath(*key.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"retain")
        paths.append(path)
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: backend)

    for key, path in zip(keys, paths, strict=True):
        assert not await delete_owned_event_image(f"/static/{key}", event_id=event_id)
        assert path.exists()


class _FakeS3Client:
    def __init__(self) -> None:
        self.deleted: list[dict[str, str]] = []

    async def delete_object(self, **kwargs: str) -> None:
        self.deleted.append(kwargs)


@pytest.mark.asyncio
async def test_s3_event_image_deletes_only_matching_bucket_key(monkeypatch):
    event_id = uuid4()
    client = _FakeS3Client()
    backend = S3Storage(
        bucket="media",
        base_url="https://cdn.example.test/media",
        client=client,
    )
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: backend)
    owned_key = f"tmp/event_images/event_{event_id}_{'c' * 32}.jpg"
    owned_url = f"https://cdn.example.test/media/{owned_key}"
    foreign_key = f"tmp/event_images/event_{uuid4()}_{'d' * 32}.jpg"

    assert not await delete_owned_event_image(
        f"https://other.example.test/media/{owned_key}", event_id=event_id
    )
    assert not await delete_owned_event_image(
        f"https://cdn.example.test/media/{foreign_key}", event_id=event_id
    )
    assert client.deleted == []

    assert await delete_owned_event_image(owned_url, event_id=event_id)
    assert client.deleted == [{"Bucket": "media", "Key": owned_key}]
