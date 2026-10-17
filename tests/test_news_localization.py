from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.models as models
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.news_media import canonical_news_image_key
from app.services.news_service import NewsService
from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend


@pytest.fixture
def news_service(db_session):
    uow = uow_from_session(db_session)
    vector = MagicMock()

    async def _embed(*args, **kwargs):
        return [0.1] * 1536

    vector.get_embedding.side_effect = _embed
    return NewsService(uow, vector)


def _generated_news_image_url() -> str:
    backend = _get_storage_backend()
    key = f"news_images/news_{uuid4().hex}.jpg"
    assert isinstance(backend, (S3Storage, StaticFSStorage))
    base_url = backend.base_url.rstrip("/")
    image_url = f"{base_url}/{key}" if base_url else f"/{key}"
    assert canonical_news_image_key(image_url) == key
    return image_url


def _assert_news_headers(response, expected_language: str) -> None:
    assert response.headers.get("Content-Language") == expected_language
    vary_header = response.headers.get("Vary", "")
    vary_values = {value.strip() for value in vary_header.split(",") if value.strip()}
    assert "Accept-Language" in vary_values
    assert (
        response.headers.get("Cache-Control")
        == "public, max-age=60, stale-while-revalidate=120"
    )


@pytest.mark.asyncio
async def test_news_localization_preference(async_client, db_session):
    primary = models.News(
        title="Новость дня",
        content="Русский текст",
        title_en="Daily News",
        content_en="English text",
    )
    fallback = models.News(title="Только русский", content="Контент без перевода")
    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)

    response_ru = await async_client.get("/news", headers={"Accept-Language": "ru"})
    assert response_ru.status_code == 200
    data_ru = {item["id"]: item for item in response_ru.json()["items"]}
    assert data_ru[str(primary.id)]["title"] == "Новость дня"
    assert data_ru[str(primary.id)]["content"] == "Русский текст"
    assert data_ru[str(primary.id)]["title_en"] == "Daily News"
    assert data_ru[str(primary.id)]["content_en"] == "English text"

    response_en = await async_client.get("/news", headers={"Accept-Language": "en"})
    assert response_en.status_code == 200
    data_en = {item["id"]: item for item in response_en.json()["items"]}
    assert data_en[str(primary.id)]["title"] == "Daily News"
    assert data_en[str(primary.id)]["content"] == "English text"
    assert data_en[str(fallback.id)]["title"] == "Только русский"
    assert data_en[str(fallback.id)]["content"] == "Контент без перевода"

    detail_en = await async_client.get(
        f"/news/{primary.id}", headers={"Accept-Language": "en"}
    )
    assert detail_en.status_code == 200
    payload_en = detail_en.json()
    assert payload_en["title"] == "Daily News"
    assert payload_en["content"] == "English text"
    assert payload_en["title_en"] == "Daily News"

    detail_ru = await async_client.get(
        f"/news/{fallback.id}", headers={"Accept-Language": "en"}
    )
    assert detail_ru.status_code == 200
    payload_ru = detail_ru.json()
    assert payload_ru["title"] == "Только русский"
    assert payload_ru["content"] == "Контент без перевода"
    assert payload_ru["title_en"] is None


@pytest.mark.asyncio
async def test_news_list_localization_headers_cache(
    async_client, db_session, fake_cache
):
    _ = fake_cache
    record = models.News(
        title="Новость дня",
        content="Русский текст",
        title_en="Daily News",
        content_en="English text",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    headers = {"Accept-Language": "en"}

    first = await async_client.get("/news", headers=headers)
    assert first.status_code == 200
    _assert_news_headers(first, "en")
    etag = first.headers.get("ETag")
    assert etag

    not_modified = await async_client.get(
        "/news", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    _assert_news_headers(not_modified, "en")
    assert not_modified.headers.get("ETag") == etag

    cached = await async_client.get("/news", headers=headers)
    assert cached.status_code == 200
    _assert_news_headers(cached, "en")
    assert cached.headers.get("ETag") == etag


@pytest.mark.asyncio
async def test_news_detail_localization_headers_cache(
    async_client, db_session, fake_cache
):
    _ = fake_cache
    record = models.News(
        title="Новость дня",
        content="Русский текст",
        title_en="Daily News",
        content_en="English text",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    headers = {"Accept-Language": "en"}

    first = await async_client.get(f"/news/{record.id}", headers=headers)
    assert first.status_code == 200
    _assert_news_headers(first, "en")
    etag = first.headers.get("ETag")
    assert etag

    not_modified = await async_client.get(
        f"/news/{record.id}", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    _assert_news_headers(not_modified, "en")
    assert not_modified.headers.get("ETag") == etag

    cached = await async_client.get(f"/news/{record.id}", headers=headers)
    assert cached.status_code == 200
    _assert_news_headers(cached, "en")
    assert cached.headers.get("ETag") == etag


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_kwargs, expected_changes",
    [
        ({"title_en": "Updated English"}, {"title_en": "Updated English"}),
        (
            {"image_url": None},
            {"image_url": None},
        ),
    ],
)
async def test_partial_news_updates_keep_other_fields(
    payload_kwargs,
    expected_changes,
    db_session,
    user_factory,
    news_service,
    monkeypatch,
):
    admin = await user_factory(role="admin")
    record = models.News(
        title="Новость дня",
        content="Русский текст",
        title_en="Daily News",
        content_en="English text",
        image_url="/static/news_images/original.png",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    original_values = {
        "title": record.title,
        "content": record.content,
        "title_en": record.title_en,
        "content_en": record.content_en,
        "image_url": record.image_url,
    }

    update_values = dict(payload_kwargs)
    expected_changes = dict(expected_changes)
    update_kwargs = {}
    replace_asset = None
    if "image_url" in update_values:
        image_url = _generated_news_image_url()
        update_values["image_url"] = image_url
        expected_changes["image_url"] = image_url
        replace_asset = AsyncMock(return_value=True)
        monkeypatch.setattr(
            news_service.repo, "replace_news_media_asset", replace_asset
        )
        update_kwargs["owner_user_id"] = admin.id

    payload = schemas.NewsUpdate(**update_values)
    await news_service.update_news(
        record.id,
        payload,
        **update_kwargs,
    )
    if replace_asset is not None:
        replace_asset.assert_awaited_once_with(
            image_url,
            owner_user_id=admin.id,
            news_id=record.id,
        )

    stored = await db_session.get(models.News, record.id)
    assert stored is not None

    for field, expected in expected_changes.items():
        assert getattr(stored, field) == expected

    for field, original in original_values.items():
        if field not in expected_changes:
            assert getattr(stored, field) == original
