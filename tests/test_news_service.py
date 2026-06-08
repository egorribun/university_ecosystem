from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.models as models
from app.schemas import schemas
from app.schemas.dtos.news import NewsDTO, NewsListingDTO
from app.services.news_service import NewsService


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.db = AsyncMock()
    repo.db.commit = AsyncMock()
    repo.db.refresh = AsyncMock()
    # Mock return values for methods to avoid awaiting None
    repo.list_news.return_value = []
    return repo


@pytest.fixture
def mock_vector_service():
    vs = AsyncMock()
    vs.get_embedding.return_value = [0.1, 0.2]
    return vs


@pytest.fixture
def mock_uow(mock_repo):
    uow = AsyncMock()
    uow.news = mock_repo
    uow.session = mock_repo.db
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.rollback = AsyncMock()
    return uow


@pytest.fixture
def news_service(mock_uow, mock_vector_service):
    return NewsService(uow=mock_uow, vector_service=mock_vector_service)


@pytest.mark.asyncio
async def test_list_news(news_service, mock_uow, mock_repo, mock_vector_service):
    # Test with search to trigger vector service
    search_query = "something"

    mock_repo.list_news.return_value = [
        NewsListingDTO(
            news=NewsDTO(
                id=uuid4(),
                title="News",
                content="Content",
                created_at=datetime.now(UTC),
                author_id=uuid4(),
                title_en=None,
                content_en=None,
                image_url=None,
            ),
            likes_count=5,
            comments_count=2,
            is_liked=True,
        )
    ]

    await news_service.list_news(search=search_query)

    mock_vector_service.get_embedding.assert_awaited_once_with(search_query)
    mock_repo.list_news.assert_awaited_once()
    kwargs = mock_repo.list_news.call_args.kwargs
    assert kwargs["search_query"] == search_query
    assert kwargs["query_embedding"] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_create_news(news_service, mock_uow, mock_repo):
    data = schemas.NewsCreate(title="News", content="Content")

    start_event_id = 1
    mock_news = MagicMock(spec=models.News)
    mock_news.id = start_event_id
    mock_news.title = "News"
    mock_repo.create.return_value = mock_news

    result = await news_service.create_news(data)

    mock_repo.create.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    assert result == mock_news


@pytest.mark.asyncio
async def test_toggle_like(news_service, mock_uow, mock_repo):
    news_id = 1
    user_id = 2
    mock_repo.toggle_like.return_value = True

    result = await news_service.toggle_like(news_id, user_id)

    mock_repo.toggle_like.assert_awaited_once_with(news_id, user_id)
    mock_uow.commit.assert_awaited_once()
    assert result is True


# --------------------------------------------------------------------------- #
# get_news / get_news_with_details / get_news_item — interaction enrichment    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_news_enriches_with_interactions(news_service, mock_repo):
    news_id, user_id = uuid4(), uuid4()
    news_obj = MagicMock()
    mock_repo.get_with_interactions.return_value = (5, True)
    mock_repo.get.return_value = news_obj

    result = await news_service.get_news(news_id, user_id)

    assert result is news_obj
    assert result.likes_count == 5
    assert result.is_liked is True


@pytest.mark.asyncio
async def test_get_news_with_details_none_when_missing(news_service, mock_repo):
    mock_repo.get.return_value = None
    assert await news_service.get_news_with_details(uuid4(), uuid4()) is None


@pytest.mark.asyncio
async def test_get_news_with_details_enriches(news_service, mock_repo):
    news_obj = MagicMock()
    mock_repo.get.return_value = news_obj
    mock_repo.get_with_interactions.return_value = (3, False)

    result = await news_service.get_news_with_details(uuid4(), uuid4())

    assert result is news_obj
    assert result.likes_count == 3
    assert result.is_liked is False


@pytest.mark.asyncio
async def test_get_news_item_passthrough(news_service, mock_repo):
    sentinel = MagicMock()
    mock_repo.get.return_value = sentinel
    assert await news_service.get_news_item(uuid4()) is sentinel


# --------------------------------------------------------------------------- #
# update_news / delete_news — not-found guards + post-commit file cleanup      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_update_news_missing_raises(news_service, mock_repo):
    mock_repo.get.return_value = None
    with pytest.raises(ValueError, match="news_not_found"):
        await news_service.update_news(uuid4(), schemas.NewsUpdate(title="x"))


@pytest.mark.asyncio
async def test_update_news_deletes_old_image_on_change(
    news_service, mock_uow, mock_repo
):
    existing = MagicMock()
    existing.image_url = "old.png"
    updated = MagicMock()
    updated.image_url = "new.png"
    mock_repo.get.return_value = existing
    mock_repo.update.return_value = updated

    with patch("app.utils.files.delete_static_file", new=AsyncMock()) as del_file:
        result = await news_service.update_news(
            uuid4(), schemas.NewsUpdate(image_url="new.png")
        )

    assert result is updated
    mock_uow.commit.assert_awaited_once()
    del_file.assert_awaited_once_with("old.png")


@pytest.mark.asyncio
async def test_delete_news_missing_returns_false(news_service, mock_repo):
    mock_repo.get.return_value = None
    assert await news_service.delete_news(uuid4()) is False


@pytest.mark.asyncio
async def test_delete_news_removes_image(news_service, mock_uow, mock_repo):
    existing = MagicMock()
    existing.image_url = "img.png"
    mock_repo.get.return_value = existing

    with patch("app.utils.files.delete_static_file", new=AsyncMock()) as del_file:
        assert await news_service.delete_news(uuid4()) is True

    mock_uow.commit.assert_awaited_once()
    del_file.assert_awaited_once_with("img.png")


# --------------------------------------------------------------------------- #
# comments — create + update/delete permission + not-found branches            #
# --------------------------------------------------------------------------- #


def _comment_dto(user_id):
    from app.schemas.dtos.news import NewsCommentDTO

    return NewsCommentDTO(
        id=uuid4(),
        news_id=uuid4(),
        user_id=user_id,
        content="hi",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_create_comment_returns_dto(news_service, mock_repo):
    uid = uuid4()
    mock_repo.create_comment.return_value = _comment_dto(uid)
    out = await news_service.create_comment(uuid4(), uid, "hi")
    assert out.user_id == uid


@pytest.mark.asyncio
async def test_update_comment_not_found_and_forbidden(news_service, mock_repo):
    mock_repo.get_comment.return_value = None
    with pytest.raises(LookupError, match="comment_not_found"):
        await news_service.update_comment(uuid4(), uuid4(), "x")

    mock_repo.get_comment.return_value = MagicMock(user_id=uuid4())
    with pytest.raises(PermissionError, match="forbidden"):
        await news_service.update_comment(uuid4(), uuid4(), "x")


@pytest.mark.asyncio
async def test_update_comment_owner_succeeds(news_service, mock_repo):
    owner = uuid4()
    mock_repo.get_comment.return_value = MagicMock(user_id=owner)
    mock_repo.update_comment.return_value = _comment_dto(owner)
    out = await news_service.update_comment(uuid4(), owner, "edited")
    assert out.user_id == owner


@pytest.mark.asyncio
async def test_delete_comment_permissions(news_service, mock_uow, mock_repo):
    mock_repo.get_comment.return_value = None
    with pytest.raises(LookupError):
        await news_service.delete_comment(uuid4(), uuid4())

    mock_repo.get_comment.return_value = MagicMock(user_id=uuid4())
    with pytest.raises(PermissionError):
        await news_service.delete_comment(uuid4(), uuid4(), is_admin=False)

    # Admin override deletes even when not the author.
    mock_repo.get_comment.return_value = MagicMock(user_id=uuid4())
    await news_service.delete_comment(uuid4(), uuid4(), is_admin=True)
    mock_uow.commit.assert_awaited()


@pytest.mark.asyncio
async def test_get_interactions_passthrough(news_service, mock_repo):
    sentinel = MagicMock()
    mock_repo.get_interactions.return_value = sentinel
    out = await news_service.get_interactions(uuid4(), uuid4())
    assert out is sentinel
