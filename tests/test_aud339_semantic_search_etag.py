from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

import app.api.events as events_api
import app.api.news as news_api
from tests.conftest import call_injected

CYRILLIC_QUERY = "\u041d\u043e\u0432\u043e\u0441\u0442\u0438"
CASE_VARIANT_QUERY = "\u043d\u043e\u0432\u043e\u0441\u0442\u0438"


@pytest.mark.parametrize(
    ("api", "version_loader_name", "dependency_name"),
    [
        (news_api, "_get_news_list_version", "NewsService"),
        (events_api, "_get_events_list_version", "EventService"),
    ],
    ids=["news", "events"],
)
@pytest.mark.asyncio
async def test_semantic_search_cyrillic_etag_is_ascii_and_covers_inputs(
    api: Any,
    version_loader_name: str,
    dependency_name: str,
) -> None:
    version = "v1"

    async def invoke(
        *,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
        locale: str = "en",
        if_none_match: str | None = None,
    ) -> tuple[object, Response, AsyncMock]:
        nonlocal version
        response = Response()
        vector = AsyncMock()
        vector.get_embedding.return_value = [0.1, 0.2]
        vector.search_similar.return_value = []
        service = MagicMock()
        request = SimpleNamespace(
            query_params={},
            headers={"Accept-Language": locale},
            app=SimpleNamespace(state=SimpleNamespace(cache=object())),
        )
        with (
            patch.object(api, "get_cache", return_value=object()),
            patch.object(
                api,
                version_loader_name,
                new_callable=AsyncMock,
                return_value=version,
            ),
        ):
            result = await call_injected(
                api.semantic_search,
                request,
                response,
                query=query,
                limit=limit,
                min_score=min_score,
                if_none_match=if_none_match,
                _user=SimpleNamespace(id=uuid.UUID(int=1)),
                provides={
                    "AsyncDatabaseSession": AsyncMock(),
                    "VectorService": vector,
                    dependency_name: service,
                },
            )
        return result, response, vector

    result, response, vector = await invoke(query=CYRILLIC_QUERY)
    assert result == []
    etag = response.headers["ETag"]
    assert etag.isascii()
    assert len(etag) <= 96
    vector.get_embedding.assert_awaited_once_with(CYRILLIC_QUERY)

    repeated, _, _ = await invoke(query=CYRILLIC_QUERY, if_none_match=etag)
    assert isinstance(repeated, Response)
    assert repeated.status_code == 304
    assert repeated.headers["ETag"] == etag

    changed_query, changed_query_response, changed_query_vector = await invoke(
        query=CASE_VARIANT_QUERY
    )
    assert changed_query == []
    assert changed_query_response.headers["ETag"] != etag
    changed_query_vector.get_embedding.assert_awaited_once_with(CASE_VARIANT_QUERY)

    changed_limit, changed_limit_response, _ = await invoke(
        query=CYRILLIC_QUERY, limit=6
    )
    assert changed_limit == []
    assert changed_limit_response.headers["ETag"] != etag

    changed_score, changed_score_response, _ = await invoke(
        query=CYRILLIC_QUERY, min_score=0.8
    )
    assert changed_score == []
    assert changed_score_response.headers["ETag"] != etag

    changed_locale, changed_locale_response, _ = await invoke(
        query=CYRILLIC_QUERY, locale="ru"
    )
    assert changed_locale == []
    assert changed_locale_response.headers["ETag"] != etag

    version = "v2"
    changed_version, changed_version_response, _ = await invoke(query=CYRILLIC_QUERY)
    assert changed_version == []
    assert changed_version_response.headers["ETag"] != etag
