from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.models as models
from app.services import content_media
from app.services.content_media import delete_owned_event_image
from app.services.storage import S3Storage, StaticFSStorage


async def _persist_event(db_session, user: models.User) -> models.Event:
    event = models.Event(
        title="Reference cleanup test",
        description="image ownership fixture",
        location="",
        event_type="workshop",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


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


@pytest.mark.asyncio
async def test_event_image_rejects_non_uuid_owner_before_resolving_storage(monkeypatch):
    resolve_backend = MagicMock()
    monkeypatch.setattr(content_media, "_get_storage_backend", resolve_backend)

    deleted = await delete_owned_event_image(
        "/static/tmp/event_images/event_123_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
        event_id=123,
    )

    assert deleted is False
    resolve_backend.assert_not_called()


@pytest.mark.asyncio
async def test_event_image_rejects_unresolvable_static_url_and_unknown_backend(
    tmp_path, monkeypatch
):
    local_backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: local_backend)

    unresolvable_event_id = uuid4()
    assert not await delete_owned_event_image(
        "https://foreign.example/tmp/event_images/event_"
        f"{unresolvable_event_id}_{'e' * 32}.jpg",
        event_id=unresolvable_event_id,
    )

    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: object())
    unknown_backend_event_id = uuid4()
    assert not await delete_owned_event_image(
        f"/static/tmp/event_images/event_{unknown_backend_event_id}_{'f' * 32}.jpg",
        event_id=unknown_backend_event_id,
    )


@pytest.mark.asyncio
async def test_local_event_image_rejects_unresolvable_traversal_before_delete(
    tmp_path, monkeypatch
):
    from unittest.mock import AsyncMock

    event_id = uuid4()
    filename = f"event_{event_id}_{'a' * 32}.jpg"
    outside_base = tmp_path / "tmp" / "event_images" / filename
    outside_base.parent.mkdir(parents=True)
    outside_base.write_bytes(b"must remain outside static root")

    backend = StaticFSStorage(tmp_path / "static", base_url="/static")
    delete_file = AsyncMock()
    monkeypatch.setattr(backend, "delete_file", delete_file)
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: backend)
    invalid_url = f"/static/../tmp/event_images/{filename}"

    assert not await delete_owned_event_image(invalid_url, event_id=event_id)
    delete_file.assert_not_awaited()
    assert outside_base.read_bytes() == b"must remain outside static root"


@pytest.mark.asyncio
async def test_reference_aware_cleanup_rejects_unowned_inputs_before_query(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from app.services.content_media import delete_unreferenced_owned_event_image

    db_session = SimpleNamespace(execute=AsyncMock())
    event_id = uuid4()
    owned_url = f"/static/tmp/event_images/event_{event_id}_{'a' * 32}.png"
    resolve_backend = MagicMock(return_value=object())
    monkeypatch.setattr(content_media, "_get_storage_backend", resolve_backend)

    assert not await delete_unreferenced_owned_event_image(
        owned_url, event_id=123, db_session=db_session
    )
    resolve_backend.assert_not_called()

    assert not await delete_unreferenced_owned_event_image(
        owned_url, event_id=event_id, db_session=db_session
    )
    resolve_backend.assert_called_once_with()

    local_backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: local_backend)
    malformed_url = "/static/tmp/event_images/legacy.png"
    assert not await delete_unreferenced_owned_event_image(
        malformed_url, event_id=event_id, db_session=db_session
    )
    db_session.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "reference_kind", ["unsupported-host", "different-key-same-leaf"]
)
@pytest.mark.asyncio
async def test_reference_aware_s3_cleanup_retains_unparseable_or_same_leaf_reference(
    reference_kind, db_session, user_factory, monkeypatch
):
    from app.services.content_media import delete_unreferenced_owned_event_image
    from app.services.storage import S3Storage

    client = AsyncMock()
    storage = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example.test/uploads",
    )
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: storage)
    image_owner = await user_factory(role="admin")
    other_author = await user_factory(role="admin")
    owner_event = await _persist_event(db_session, image_owner)
    referencing_event = await _persist_event(db_session, other_author)
    filename = f"event_{owner_event.id}_{'b' * 32}.png"
    storage_key = f"tmp/event_images/{filename}"
    owner_url = f"{storage.base_url}/{storage_key}"
    if reference_kind == "unsupported-host":
        reference_url = f"https://unconfigured.example.test/uploads/{filename}"
    else:
        reference_url = f"s3://test-bucket/legacy/event_images/{filename}"

    owner_event.image_url = owner_url
    referencing_event.image_url = reference_url
    await db_session.commit()
    replacement_key = "tmp/event_images/replacement.png"
    owner_event.image_url = f"{storage.base_url}/{replacement_key}"
    await db_session.commit()

    removed = await delete_unreferenced_owned_event_image(
        owner_url, event_id=owner_event.id, db_session=db_session
    )

    assert removed is False
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_s3_cleanup_ignores_filename_substring_in_different_leaf(
    db_session, user_factory, monkeypatch
):
    from app.services.content_media import delete_unreferenced_owned_event_image
    from app.services.storage import S3Storage

    client = AsyncMock()
    storage = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example.test/uploads",
    )
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: storage)
    owner = await user_factory(role="admin")
    other_author = await user_factory(role="admin")
    owner_event = await _persist_event(db_session, owner)
    reference_event = await _persist_event(db_session, other_author)
    filename = f"event_{owner_event.id}_{'e' * 32}.png"
    target_key = f"tmp/event_images/{filename}"
    target_url = f"{storage.base_url}/{target_key}"
    owner_event.image_url = target_url
    reference_event.image_url = f"{storage.base_url}/archive/{filename}.backup"
    await db_session.commit()

    replacement_key = "tmp/event_images/replacement.png"
    owner_event.image_url = f"{storage.base_url}/{replacement_key}"
    await db_session.commit()

    removed = await delete_unreferenced_owned_event_image(
        target_url, event_id=owner_event.id, db_session=db_session
    )

    assert removed is True
    client.delete_object.assert_awaited_once_with(Bucket="test-bucket", Key=target_key)


@pytest.mark.asyncio
async def test_reference_aware_s3_cleanup_deletes_committed_unreferenced_object(
    db_session, user_factory, monkeypatch
):
    from app.services.content_media import delete_unreferenced_owned_event_image
    from app.services.storage import S3Storage

    client = AsyncMock()
    storage = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example.test/uploads",
    )
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: storage)
    owner = await user_factory(role="admin")
    event = await _persist_event(db_session, owner)
    filename = f"event_{event.id}_{'c' * 32}.png"
    storage_key = f"tmp/event_images/{filename}"
    owner_url = f"{storage.base_url}/{storage_key}"
    event.image_url = owner_url
    await db_session.commit()
    replacement_key = "tmp/event_images/replacement.png"
    event.image_url = f"{storage.base_url}/{replacement_key}"
    await db_session.commit()

    removed = await delete_unreferenced_owned_event_image(
        owner_url, event_id=event.id, db_session=db_session
    )

    assert removed is True
    client.delete_object.assert_awaited_once_with(Bucket="test-bucket", Key=storage_key)


@pytest.mark.asyncio
async def test_reference_aware_cleanup_retains_on_non_string_query_result(
    monkeypatch,
):
    from types import SimpleNamespace

    from app.services.content_media import delete_unreferenced_owned_event_image
    from app.services.storage import S3Storage

    class _ResultWithInvalidImageValue:
        def scalars(self):
            return iter([None])

    client = AsyncMock()
    storage = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example.test/uploads",
    )
    monkeypatch.setattr(content_media, "_get_storage_backend", lambda: storage)
    db_session = SimpleNamespace(
        execute=AsyncMock(return_value=_ResultWithInvalidImageValue())
    )
    event_id = uuid4()
    filename = f"event_{event_id}_{'d' * 32}.png"
    storage_key = f"tmp/event_images/{filename}"
    owner_url = f"{storage.base_url}/{storage_key}"

    removed = await delete_unreferenced_owned_event_image(
        owner_url, event_id=event_id, db_session=db_session
    )

    assert removed is False
    db_session.execute.assert_awaited_once()
    client.delete_object.assert_not_awaited()
