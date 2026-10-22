from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

import app.models as models
import app.services.news_media as news_media
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.news_service import NewsImageOwnershipError, NewsService
from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend


def _generated_news_image_url() -> str:
    backend = _get_storage_backend()
    key = f"news_images/news_{uuid4().hex}.jpg"
    assert isinstance(backend, (S3Storage, StaticFSStorage))
    base_url = backend.base_url.rstrip("/")
    return f"{base_url}/{key}" if base_url else f"/{key}"


@pytest.mark.asyncio
async def test_upload_owner_can_claim_image_but_another_admin_cannot(
    db_session, user_factory
):
    owner = await user_factory(role="admin")
    foreign_admin = await user_factory(role="admin")
    service = NewsService(uow_from_session(db_session), AsyncMock())
    image_url = _generated_news_image_url()
    await service.register_uploaded_image(image_url, owner_user_id=owner.id)

    news = await service.create_news(
        schemas.NewsCreate(title="Owned image", content="Body", image_url=image_url),
        owner_user_id=owner.id,
    )

    asset = await db_session.scalar(
        select(models.NewsMediaAsset).where(
            models.NewsMediaAsset.storage_url == image_url
        )
    )
    assert asset is not None
    assert asset.owner_user_id == owner.id
    assert asset.news_id == news.id

    with pytest.raises(NewsImageOwnershipError):
        await service.create_news(
            schemas.NewsCreate(
                title="Foreign reuse", content="Body", image_url=image_url
            ),
            owner_user_id=foreign_admin.id,
        )

    assert (
        await db_session.scalar(
            select(models.News.id).where(models.News.title == "Foreign reuse")
        )
        is None
    )


@pytest.mark.asyncio
async def test_changed_legacy_or_noncanonical_image_is_rejected_without_adoption(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    record = models.News(
        title="Legacy", content="Body", image_url="/static/news_images/shared.png"
    )
    admin_id = admin.id
    db_session.add(record)
    await db_session.flush()
    record_id = record.id
    await db_session.commit()
    service = NewsService(uow_from_session(db_session), AsyncMock())

    with pytest.raises(NewsImageOwnershipError):
        await service.update_news(
            record_id,
            schemas.NewsUpdate(image_url="https://foreign.example/shared.png"),
            owner_user_id=admin_id,
        )

    await service.update_news(
        record_id,
        schemas.NewsUpdate(image_url="/static/news_images/shared.png"),
        owner_user_id=admin_id,
    )
    await db_session.refresh(record)
    assert record.image_url == "/static/news_images/shared.png"
    assert await db_session.scalar(select(models.NewsMediaAsset.id)) is None


@pytest.mark.asyncio
async def test_canonical_looking_but_unregistered_url_is_rejected(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    service = NewsService(uow_from_session(db_session), AsyncMock())

    with pytest.raises(NewsImageOwnershipError):
        await service.create_news(
            schemas.NewsCreate(
                title="Unregistered",
                content="Body",
                image_url=_generated_news_image_url(),
            ),
            owner_user_id=admin.id,
        )

    assert await db_session.scalar(select(models.News.id)) is None


def test_canonical_news_image_key_fails_closed_for_storage_aliases(monkeypatch):
    backend = StaticFSStorage(base_dir=Path("."))
    monkeypatch.setattr(news_media, "_get_storage_backend", lambda: backend)

    assert news_media.canonical_news_image_key(None) is None
    assert news_media.canonical_news_image_key("../news_images/file.jpg") is None
    assert (
        news_media.canonical_news_image_key(
            "/static/news_images/not-a-generated-key.jpg"
        )
        is None
    )

    monkeypatch.setattr(news_media, "_get_storage_backend", lambda: object())
    assert (
        news_media.canonical_news_image_key(
            "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg"
        )
        is None
    )


def test_canonical_news_image_key_accepts_only_configured_s3_url(monkeypatch):
    backend = S3Storage(bucket="news-media-test", base_url="https://cdn.example")
    monkeypatch.setattr(news_media, "_get_storage_backend", lambda: backend)
    key = "news_images/news_0123456789abcdef0123456789abcdef.webp"

    assert news_media.canonical_news_image_key(f"https://cdn.example/{key}") == key
    assert news_media.canonical_news_image_key(f"https://other.example/{key}") is None


@pytest.mark.asyncio
async def test_owned_replacement_claims_new_key_and_releases_old_association(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    old_image_url = _generated_news_image_url()
    record = models.News(title="Replace", content="Body", image_url=old_image_url)
    old_asset = models.NewsMediaAsset(
        storage_url=old_image_url,
        owner_user_id=admin.id,
    )
    db_session.add_all([record, old_asset])
    await db_session.flush()
    old_asset.news_id = record.id
    await db_session.commit()
    await db_session.refresh(record)
    service = NewsService(uow_from_session(db_session), AsyncMock())
    image_url = _generated_news_image_url()
    await service.register_uploaded_image(image_url, owner_user_id=admin.id)

    updated = await service.update_news(
        record.id,
        schemas.NewsUpdate(image_url=image_url),
        owner_user_id=admin.id,
    )

    asset = await db_session.scalar(
        select(models.NewsMediaAsset).where(
            models.NewsMediaAsset.storage_url == image_url
        )
    )
    await db_session.refresh(old_asset)
    assert updated.image_url == image_url
    assert asset is not None
    assert asset.news_id == record.id
    assert old_asset.news_id is None


@pytest.mark.asyncio
async def test_failed_replacement_rolls_back_old_asset_release(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    other_admin = await user_factory(role="admin")
    old_image_url = _generated_news_image_url()
    record = models.News(
        title="Keep old image", content="Body", image_url=old_image_url
    )
    admin_id = admin.id
    other_admin_id = other_admin.id
    old_asset = models.NewsMediaAsset(
        storage_url=old_image_url,
        owner_user_id=admin_id,
    )
    db_session.add_all([record, old_asset])
    await db_session.flush()
    record_id = record.id
    old_asset.news_id = record_id
    foreign_image_url = _generated_news_image_url()
    foreign_asset = models.NewsMediaAsset(
        storage_url=foreign_image_url,
        owner_user_id=other_admin_id,
    )
    db_session.add(foreign_asset)
    await db_session.commit()
    service = NewsService(uow_from_session(db_session), AsyncMock())

    with pytest.raises(NewsImageOwnershipError):
        await service.update_news(
            record_id,
            schemas.NewsUpdate(image_url=foreign_image_url),
            owner_user_id=admin_id,
        )

    await db_session.refresh(record)
    await db_session.refresh(old_asset)
    foreign_asset_after = await db_session.scalar(
        select(models.NewsMediaAsset).where(
            models.NewsMediaAsset.storage_url == foreign_image_url
        )
    )
    assert record.image_url == old_image_url
    assert old_asset.news_id == record_id
    assert foreign_asset_after is not None
    assert foreign_asset_after.owner_user_id == other_admin_id
    assert foreign_asset_after.news_id is None


@pytest.mark.asyncio
async def test_replacement_rejects_claimed_image_before_release(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    old_image_url = _generated_news_image_url()
    claimed_image_url = _generated_news_image_url()
    current_news = models.News(
        title="Keep current image", content="Body", image_url=old_image_url
    )
    other_news = models.News(
        title="Keep claimed image", content="Body", image_url=claimed_image_url
    )
    old_asset = models.NewsMediaAsset(
        storage_url=old_image_url,
        owner_user_id=admin.id,
    )
    claimed_asset = models.NewsMediaAsset(
        storage_url=claimed_image_url,
        owner_user_id=admin.id,
    )
    db_session.add_all([current_news, other_news, old_asset, claimed_asset])
    await db_session.flush()
    old_asset.news_id = current_news.id
    claimed_asset.news_id = other_news.id
    await db_session.commit()
    service = NewsService(uow_from_session(db_session), AsyncMock())

    with pytest.raises(NewsImageOwnershipError):
        await service.update_news(
            current_news.id,
            schemas.NewsUpdate(image_url=claimed_image_url),
            owner_user_id=admin.id,
        )

    await db_session.refresh(current_news)
    await db_session.refresh(other_news)
    await db_session.refresh(old_asset)
    await db_session.refresh(claimed_asset)
    assert current_news.image_url == old_image_url
    assert other_news.image_url == claimed_image_url
    assert old_asset.news_id == current_news.id
    assert claimed_asset.news_id == other_news.id


@pytest.mark.asyncio
async def test_deleted_uploader_cannot_claim_or_transfer_asset(
    db_session, user_factory
):
    owner = await user_factory(role="admin")
    image_url = _generated_news_image_url()
    service = NewsService(uow_from_session(db_session), AsyncMock())
    await service.register_uploaded_image(image_url, owner_user_id=owner.id)

    await db_session.delete(owner)
    await db_session.commit()

    asset = await db_session.scalar(
        select(models.NewsMediaAsset).where(
            models.NewsMediaAsset.storage_url == image_url
        )
    )
    assert asset is not None
    assert asset.owner_user_id is None
    with pytest.raises(NewsImageOwnershipError):
        await service.create_news(
            schemas.NewsCreate(
                title="Deleted uploader", content="Body", image_url=image_url
            ),
            owner_user_id=uuid4(),
        )

    assert (
        await db_session.scalar(
            select(models.News.id).where(models.News.title == "Deleted uploader")
        )
        is None
    )
