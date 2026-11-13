"""Route-level behaviour of semantic-only search when no embeddings provider is set.

Master plan Search: direct semantic-only routes must report unavailability
explicitly and must never compute results from a zero vector. These tests run
the real ``VectorService`` (``get_embedding`` is not mocked) with an empty
``embedding_api_key``, so the provider HTTP call and both vector-search methods
are the only things that could run; each is replaced by a mock that must stay
un-awaited.

Ordinary text search for events remains available without the key.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

import app.models as models
from app.api.deps import get_current_user
from app.core.config import settings
from app.main import app
from app.schemas import schemas
from app.services.vector_service import (
    SEMANTIC_SEARCH_UNAVAILABLE_DETAIL,
    VectorService,
)
from tests.conftest import install_dishka_override


@dataclass
class _ProviderSpy:
    service: VectorService
    provider_post: AsyncMock
    search_similar: AsyncMock
    search_similar_with_scores: AsyncMock


@asynccontextmanager
async def _no_embeddings_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_ProviderSpy]:
    """Enable semantic search but leave the embedding key empty (no provider)."""
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "")
    service = VectorService(db=AsyncMock())
    try:
        with (
            patch.object(service._client, "post", new_callable=AsyncMock) as post,
            patch.object(
                VectorService, "search_similar", new_callable=AsyncMock
            ) as search_similar,
            patch.object(
                VectorService,
                "search_similar_with_scores",
                new_callable=AsyncMock,
            ) as search_with_scores,
        ):
            yield _ProviderSpy(
                service=service,
                provider_post=post,
                search_similar=search_similar,
                search_similar_with_scores=search_with_scores,
            )
    finally:
        await service.close()


@pytest.fixture
def student() -> models.User:
    user = MagicMock(spec=models.User)
    user.id = uuid.uuid4()
    user.role = "student"
    user.email = "student@example.com"
    profile = MagicMock()
    profile.full_name = "Student"
    user.profile = profile
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.mark.asyncio
async def test_news_semantic_route_reports_unavailable_without_zero_vector(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, student: models.User
) -> None:
    news_service = MagicMock()
    async with _no_embeddings_provider(monkeypatch) as spy:
        install_dishka_override(
            app, NewsService=news_service, VectorService=spy.service
        )
        with patch(
            "app.api.news._get_news_list_version", new_callable=AsyncMock
        ) as get_version:
            resp = await async_client.get(
                "/news/search/semantic", params={"query": "test query", "limit": 5}
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == 503
    assert body["detail"] == SEMANTIC_SEARCH_UNAVAILABLE_DETAIL
    spy.provider_post.assert_not_awaited()
    spy.search_similar.assert_not_awaited()
    spy.search_similar_with_scores.assert_not_awaited()
    get_version.assert_not_awaited()
    news_service.serialize_news.assert_not_called()


@pytest.mark.asyncio
async def test_events_semantic_route_reports_unavailable_without_zero_vector(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, student: models.User
) -> None:
    event_service = MagicMock()
    async with _no_embeddings_provider(monkeypatch) as spy:
        install_dishka_override(
            app, EventService=event_service, VectorService=spy.service
        )
        with patch(
            "app.api.events._get_events_list_version", new_callable=AsyncMock
        ) as get_version:
            resp = await async_client.get(
                "/events/search/semantic", params={"query": "test query", "limit": 5}
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == 503
    assert body["detail"] == SEMANTIC_SEARCH_UNAVAILABLE_DETAIL
    spy.provider_post.assert_not_awaited()
    spy.search_similar.assert_not_awaited()
    spy.search_similar_with_scores.assert_not_awaited()
    get_version.assert_not_awaited()
    event_service.serialize_event.assert_not_called()


@pytest.mark.asyncio
async def test_events_text_search_works_without_embeddings_provider(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, student: models.User
) -> None:
    event_service = MagicMock()
    event_service.get_events = AsyncMock(
        return_value=schemas.PaginatedEvents(
            items=[],
            limit=20,
            cursor=None,
            next_cursor=None,
            has_more=False,
        )
    )
    async with _no_embeddings_provider(monkeypatch) as spy:
        install_dishka_override(
            app, EventService=event_service, VectorService=spy.service
        )
        resp = await async_client.get("/events", params={"search": "term"})

    assert resp.status_code == 200
    assert resp.json()["items"] == []
    event_service.get_events.assert_awaited_once()
    assert event_service.get_events.await_args.kwargs["search"] == "term"
    spy.provider_post.assert_not_awaited()
    spy.search_similar.assert_not_awaited()
