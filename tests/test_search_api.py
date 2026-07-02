import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from httpx import AsyncClient

import app.models as models
from app.api.deps import get_current_user
from app.main import app
from app.services.search import SearchService


@pytest.fixture
def mock_user():
    user = MagicMock(spec=models.User)
    user.id = uuid.uuid4()
    user.role = "student"
    return user


@pytest.fixture
def mock_search_service():
    service = AsyncMock(spec=SearchService)
    return service


@pytest.mark.asyncio
async def test_unified_search_all_success(
    async_client: AsyncClient, mock_user, mock_search_service
):
    # Mock search service responses for news and events
    mock_search_service.search.side_effect = [
        # News results
        {
            "total": 1,
            "hits": [
                {
                    "id": "news-1",
                    "score": 1.2,
                    "source": {
                        "title": "News Title",
                        "content": "Some interesting news content here",
                    },
                    "highlights": {
                        "content": ["Some interesting <mark>news</mark> content here"]
                    },
                }
            ],
        },
        # Events results
        {
            "total": 1,
            "hits": [
                {
                    "id": "event-1",
                    "score": 0.9,
                    "source": {
                        "title": "Event Title",
                        "description": "Fun event description",
                    },
                    "highlights": {},
                }
            ],
        },
    ]

    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "test", "type": "all", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert "news" in data["results"]
        assert "events" in data["results"]

        news_results = data["results"]["news"]
        assert len(news_results) == 1
        assert news_results[0]["id"] == "news-1"
        assert news_results[0]["type"] == "news"
        assert news_results[0]["title"] == "News Title"
        assert (
            news_results[0]["summary"]
            == "Some interesting <mark>news</mark> content here"
        )
        assert news_results[0]["score"] == 1.2
        assert news_results[0]["url"] == "/news/news-1"

        event_results = data["results"]["events"]
        assert len(event_results) == 1
        assert event_results[0]["id"] == "event-1"
        assert event_results[0]["type"] == "events"
        assert event_results[0]["title"] == "Event Title"
        assert event_results[0]["summary"] == "Fun event description"
        assert event_results[0]["score"] == 0.9
        assert event_results[0]["url"] == "/events/event-1"

    finally:
        # Cleaned up by conftest
        pass
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container


@pytest.mark.asyncio
async def test_unified_search_only_news(
    async_client: AsyncClient, mock_user, mock_search_service
):
    mock_search_service.search.return_value = {
        "total": 1,
        "hits": [
            {
                "id": "news-2",
                "score": 2.0,
                "source": {"title": "Only News Title", "content": "Only news content"},
                "highlights": {},
            }
        ],
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "news-only", "type": "news", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "news" in data["results"]
        assert "events" not in data["results"]
        assert len(data["results"]["news"]) == 1
        assert data["results"]["news"][0]["id"] == "news-2"

    finally:
        # Cleaned up by conftest
        pass
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container


@pytest.mark.asyncio
async def test_unified_search_connection_error_fallback(
    async_client: AsyncClient, mock_user, mock_search_service
):
    # Simulate ConnectionError
    mock_search_service.search.side_effect = ConnectionError(
        "Failed to connect to Elasticsearch"
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "error", "type": "all"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["news"] == []
        assert data["results"]["events"] == []

    finally:
        # Cleaned up by conftest
        pass
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container


@pytest.mark.asyncio
async def test_unified_search_only_events(
    async_client: AsyncClient, mock_user, mock_search_service
):
    mock_search_service.search.return_value = {
        "total": 1,
        "hits": [
            {
                "id": "event-2",
                "score": 1.8,
                "source": {
                    "title": "Only Event Title",
                    "description": "Only event description",
                },
                "highlights": {},
            }
        ],
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "event-only", "type": "events", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data["results"]
        assert "news" not in data["results"]
        assert len(data["results"]["events"]) == 1
        assert data["results"]["events"][0]["id"] == "event-2"

    finally:
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container


@pytest.mark.asyncio
async def test_unified_search_invalid_type(
    async_client: AsyncClient, mock_user, mock_search_service
):
    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "invalid", "type": "invalid_type"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == {}

    finally:
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container


@pytest.mark.asyncio
async def test_unified_search_non_string_fallback(
    async_client: AsyncClient, mock_user, mock_search_service
):
    mock_search_service.search.return_value = {
        "total": 1,
        "hits": [
            {
                "id": "news-non-str",
                "score": 1.0,
                # value of content is None, which triggers line 112 of search.py
                "source": {"title": "Title", "content": None},
                "highlights": {},
            }
        ],
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user

    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def search_svc(self) -> SearchService:
            return mock_search_service

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        resp = await async_client.get(
            "/search",
            params={"q": "test", "type": "news"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["news"][0]["summary"] == ""

    finally:
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container
