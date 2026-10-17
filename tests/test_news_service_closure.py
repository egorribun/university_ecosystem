"""Branch closure tests for NewsService no-op cleanup paths."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.repositories.news_repository import NewsRepository
from app.schemas.dtos.news import NewsDTO, NewsListingDTO
from app.services.news_service import NewsService
from app.utils.pagination import encode_datetime_cursor


def _service():
    repo = AsyncMock()
    uow = AsyncMock()
    uow.news = repo
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    return NewsService(uow, AsyncMock()), repo


@pytest.mark.asyncio
async def test_get_news_returns_none_without_enrichment():
    service, repo = _service()
    repo.get_with_interactions.return_value = (0, False)
    repo.get.return_value = None

    assert await service.get_news(uuid4()) is None


@pytest.mark.asyncio
async def test_delete_news_commits_without_static_image_cleanup():
    service, repo = _service()
    news = MagicMock()
    news.image_url = None
    repo.get.return_value = news

    assert await service.delete_news(uuid4()) is True
    service.uow.commit.assert_awaited_once()


def _listing(created_at: datetime, news_id):
    return NewsListingDTO(
        news=NewsDTO(
            id=news_id,
            title="News",
            content="Content",
            created_at=created_at,
            author_id=uuid4(),
            title_en=None,
            content_en=None,
            image_url=None,
        ),
        likes_count=1,
        comments_count=2,
        is_liked=False,
    )


@pytest.mark.asyncio
async def test_list_news_uses_cursor_and_builds_next_cursor():
    service, repo = _service()
    first_id, second_id = uuid4(), uuid4()
    first_time = datetime(2026, 1, 2, tzinfo=UTC)
    second_time = datetime(2026, 1, 1, tzinfo=UTC)
    repo.list_news.return_value = [
        _listing(first_time, first_id),
        _listing(second_time, second_id),
    ]
    cursor = encode_datetime_cursor(second_time, str(second_id))

    result = await service.list_news(limit=1, cursor=cursor)

    assert result.has_more is True
    assert result.next_cursor is not None
    assert repo.list_news.call_args.kwargs["cursor"] == (second_time, str(second_id))


@pytest.mark.asyncio
async def test_list_news_suppresses_malformed_decoded_cursor():
    service, repo = _service()
    repo.list_news.return_value = []

    with patch("app.utils.pagination.decode_datetime_cursor", return_value=object()):
        result = await service.list_news(limit=1, cursor="malformed")

    assert result.next_cursor is None
    assert repo.list_news.call_args.kwargs["cursor"] is None


@pytest.mark.asyncio
async def test_list_news_ignores_cursor_without_decoded_value():
    service, repo = _service()
    repo.list_news.return_value = []

    with patch("app.utils.pagination.decode_datetime_cursor", return_value=None):
        result = await service.list_news(limit=1, cursor="not-decodable")

    assert result.has_more is False
    assert repo.list_news.call_args.kwargs["cursor"] is None


@pytest.mark.asyncio
async def test_list_news_ignores_empty_secondary_cursor_before_repository_cast():
    """The public ``/news?cursor=0:`` path must not cast an empty UUID."""
    db = AsyncMock()
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = []
    db.execute.return_value = db_result

    uow = MagicMock()
    uow.news = NewsRepository(db)
    service = NewsService(uow, AsyncMock())

    result = await service.list_news(limit=1, cursor="0:")

    assert result.items == []
    assert result.has_more is False
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_list_news_preserves_valid_epoch_uuid_cursor():
    service, repo = _service()
    repo.list_news.return_value = []
    cursor_id = str(uuid4())
    cursor = encode_datetime_cursor(datetime(1970, 1, 1, tzinfo=UTC), cursor_id)

    result = await service.list_news(limit=1, cursor=cursor)

    assert result.has_more is False
    assert repo.list_news.call_args.kwargs["cursor"] == (
        datetime(1970, 1, 1, tzinfo=UTC),
        cursor_id,
    )


@pytest.mark.asyncio
async def test_register_uploaded_image_rejects_noncanonical_url_before_transaction():
    from app.services.news_service import NewsImageOwnershipError

    service, repo = _service()
    with (
        patch(
            "app.services.news_service.canonical_news_image_key",
            return_value=None,
        ),
        pytest.raises(NewsImageOwnershipError, match="news_image_not_owned"),
    ):
        await service.register_uploaded_image(
            "/static/news_images/shared.png", owner_user_id=uuid4()
        )

    service.uow.__aenter__.assert_not_awaited()
    service.uow.commit.assert_not_awaited()
    repo.register_news_media_asset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_user_id", "canonical_key"),
    [
        (None, "news_images/news_0123456789abcdef0123456789abcdef.jpg"),
        (uuid4(), None),
    ],
)
async def test_create_news_rejects_unowned_image_before_opening_uow(
    owner_user_id, canonical_key
):
    from app.schemas import schemas
    from app.services.news_service import NewsImageOwnershipError

    service, repo = _service()
    image_url = "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg"
    with (
        patch(
            "app.services.news_service.canonical_news_image_key",
            return_value=canonical_key,
        ),
        pytest.raises(NewsImageOwnershipError, match="news_image_not_owned"),
    ):
        await service.create_news(
            schemas.NewsCreate(
                title="Unowned image", content="Body", image_url=image_url
            ),
            owner_user_id=owner_user_id,
        )

    service.uow.__aenter__.assert_not_awaited()
    service.uow.commit.assert_not_awaited()
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_news_clears_existing_image_without_uploader_claim():
    from app.schemas import schemas

    service, repo = _service()
    news_id = uuid4()
    existing_news = MagicMock()
    existing_news.image_url = "/static/news_images/legacy-banner.png"
    updated_news = MagicMock()
    updated_news.image_url = None
    repo.get_orm_for_update.return_value = existing_news
    repo.replace_news_media_asset.return_value = True
    repo.update.return_value = updated_news

    result = await service.update_news(
        news_id, schemas.NewsUpdate(image_url=None), owner_user_id=None
    )

    assert result is updated_news
    assert result.image_url is None
    repo.replace_news_media_asset.assert_awaited_once_with(
        None, owner_user_id=None, news_id=news_id
    )
    repo.update.assert_awaited_once_with(news_id, {"image_url": None})
    service.uow.commit.assert_awaited_once()
