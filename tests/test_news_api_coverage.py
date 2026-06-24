import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

import app.models as models
from app.api.deps import get_news_service
from app.core.container import get_notification_service
from app.main import app
from app.schemas import schemas


@pytest.fixture
def mock_notification_service():
    service = AsyncMock()
    return service


@pytest.fixture
def mock_news_service():
    service = AsyncMock()
    # Mock methods used in endpoints
    service.get_news_item.return_value = MagicMock(
        spec=models.News,
        id=uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79"),
        title="Test News",
    )
    service.create_comment.return_value = MagicMock(
        spec=models.NewsComment,
        id=uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7a"),
        content="Test Comment",
        user_id=uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7b"),
        created_at="2024-01-01",
    )
    service.update_comment.return_value = MagicMock(
        spec=models.NewsComment,
        id=uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7a"),
        content="Updated Comment",
        user_id=uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7b"),
        created_at="2024-01-01",
    )
    service.delete_comment.return_value = None

    # Mock serialize_news
    def _serialize(news, locale):
        return schemas.NewsOut(
            id=news.id,
            title="Test News",
            content="Content",
            created_at="2024-01-01T00:00:00Z",  # ISO format string for schema
            image_url=None,
            likes_count=0,
            comments_count=0,
            is_liked=False,
        )

    service.serialize_news = MagicMock(side_effect=_serialize)

    return service


@pytest.fixture
def mock_vector_service():
    vs = AsyncMock()
    vs.get_embedding.return_value = [0.1, 0.2]

    # Create a proper mock News object with all required attributes
    mock_news = MagicMock()
    mock_news.id = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7d")
    mock_news.title = "Similar News"
    mock_news.content = "Similar content"
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.author_id = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7c")
    mock_news.image_url = None
    mock_news.created_at = "2024-01-01T00:00:00Z"
    mock_news.likes = []
    mock_news.comments = []

    vs.search_similar.return_value = [mock_news]
    return vs


@pytest.mark.asyncio
async def test_news_interactions_endpoint(async_client: AsyncClient, mock_news_service):
    from app.api.deps import get_read_news_service

    app.dependency_overrides[get_read_news_service] = lambda: mock_news_service

    mock_news_service.get_interactions.return_value = {
        "likes_count": 10,
        "is_liked": True,
        "comments": [],
        "comments_count": 0,
    }

    resp = await async_client.get(f"/news/{uuid.UUID(int=1)}/interactions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["likes_count"] == 10
    assert data["is_liked"] is True

    # Cleaned up by conftest
    pass


@pytest.mark.asyncio
async def test_create_comment(
    async_client: AsyncClient,
    mock_news_service,
    mock_notification_service,
    user_factory,
):
    # Need to be authenticated

    from app.api.deps import get_current_user

    mock_user = MagicMock(spec=models.User)
    mock_user.id = uuid.UUID(int=1)
    mock_user.role = "user"
    mock_user.email = "test@example.com"
    mock_profile = MagicMock()
    mock_profile.full_name = "Test User"
    mock_user.profile = mock_profile

    app.dependency_overrides[get_news_service] = lambda: mock_news_service
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_notification_service] = lambda: (
        mock_notification_service
    )

    resp = await async_client.post(
        f"/news/{uuid.UUID(int=1)}/comment", json={"content": "Test Comment"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Test Comment"

    # Clean up
    del app.dependency_overrides[get_news_service]
    del app.dependency_overrides[get_current_user]
    del app.dependency_overrides[get_notification_service]


@pytest.mark.asyncio
async def test_update_comment(async_client: AsyncClient, mock_news_service):
    mock_user = MagicMock(spec=models.User)
    mock_user.id = uuid.UUID(int=1)
    mock_user.email = "test@example.com"
    mock_profile = MagicMock()
    mock_profile.full_name = "Test User"
    mock_user.profile = mock_profile

    from app.api.deps import get_current_user

    app.dependency_overrides[get_news_service] = lambda: mock_news_service
    app.dependency_overrides[get_current_user] = lambda: mock_user

    resp = await async_client.patch(
        f"/news/comments/{uuid.UUID(int=1)}", json={"content": "Updated Comment"}
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated Comment"

    # Test failure case
    mock_news_service.update_comment.side_effect = LookupError("Not found")
    resp = await async_client.patch(
        f"/news/comments/{uuid.UUID(int=99)}", json={"content": "Fail"}
    )
    assert resp.status_code == 404

    # Test permission error
    mock_news_service.update_comment.side_effect = PermissionError("Forbidden")
    resp = await async_client.patch(
        f"/news/comments/{uuid.UUID(int=1)}", json={"content": "Forbidden"}
    )
    assert resp.status_code == 403  # raise_forbidden returns 403

    # Cleaned up by conftest
    pass


@pytest.mark.asyncio
async def test_delete_comment(async_client: AsyncClient, mock_news_service):
    mock_user = MagicMock(spec=models.User)
    mock_user.id = 1
    mock_user.role = "user"

    from app.api.deps import get_current_user

    app.dependency_overrides[get_news_service] = lambda: mock_news_service
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Success
    resp = await async_client.delete(f"/news/comments/{uuid.UUID(int=1)}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Not found
    mock_news_service.delete_comment.side_effect = LookupError()
    resp = await async_client.delete(f"/news/comments/{uuid.UUID(int=99)}")
    assert resp.status_code == 404

    # Forbidden
    mock_news_service.delete_comment.side_effect = PermissionError()
    resp = await async_client.delete(f"/news/comments/{uuid.UUID(int=1)}")
    assert resp.status_code == 403

    # Cleaned up by conftest
    pass


@pytest.mark.asyncio
async def test_semantic_search(
    async_client: AsyncClient, mock_news_service, mock_vector_service
):
    # If semantic search relies on get_vector_service, it was probably injected directly
    # Wait, what does the router inject? Let me just mock the VectorService class in DI if it's Dishka
    # But this uses dependency_overrides, so it's FastAPI DI.
    from app.api.deps import get_current_user, get_read_news_service
    from app.core.container import get_vector_service

    mock_user = MagicMock(spec=models.User)
    mock_user.id = uuid.uuid4()
    mock_user.role = "student"
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_read_news_service] = lambda: mock_news_service
    app.dependency_overrides[get_vector_service] = lambda: mock_vector_service

    resp = await async_client.get(
        "/news/search/semantic", params={"query": "test query", "limit": 5}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    # serialize_news returns a fixed "Test News" title for any input
    assert data[0]["title"] == "Test News"

    mock_vector_service.get_embedding.assert_awaited()
    mock_vector_service.search_similar.assert_awaited()

    # Cleaned up by conftest
    pass


# Missing: upload_news_image. Requires mocking save_upload in app.api.news
@pytest.mark.asyncio
async def test_upload_news_image(async_client: AsyncClient):
    from unittest.mock import patch

    from app.api.deps import get_current_user

    mock_user = MagicMock(spec=models.User)
    mock_user.id = 1
    mock_user.role = "admin"  # Require admin

    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("app.api.news.save_upload", new_callable=AsyncMock) as mock_save:
        mock_save.return_value = "http://cdn.example.com/image.jpg"

        files = {"file": ("test.jpg", b"image data", "image/jpeg")}
        resp = await async_client.post("/news/upload_image", files=files)

        assert resp.status_code == 200
        assert resp.json()["url"] == "http://cdn.example.com/image.jpg"
        mock_save.assert_awaited()

    # Test non-admin
    mock_user.role = "user"
    resp = await async_client.post("/news/upload_image", files=files)
    assert resp.status_code == 403

    # Cleaned up by conftest
    pass
