"""Unified search endpoint combining full-text (Elasticsearch) and semantic (pgvector) search.

Wave 38: Provides a single search API for the frontend SearchDialog (Cmd+K).
"""

from __future__ import annotations

from typing import Any

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends
from fastapi import Query as QueryParam

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.services.search import SearchService

logger = get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

_NEWS_FIELDS = ["title", "content", "summary", "author_name", "tags"]
_EVENTS_FIELDS = ["title", "description", "location", "organizer_name", "category"]
_MAX_RESULTS = 10


@router.get("")
@inject
async def unified_search(
    search_svc: FromDishka[SearchService],
    q: str = QueryParam(..., min_length=1, max_length=256, description="Search query"),
    type: str = QueryParam("all", description="Search type: news, events, or all"),
    limit: int = QueryParam(
        _MAX_RESULTS, ge=1, le=50, description="Max results per type"
    ),
    _user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Unified search across news and events.

    Combines Elasticsearch full-text search.
    Results are grouped by type for the frontend SearchDialog.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    search_types = [type] if type != "all" else ["news", "events"]

    for search_type in search_types:
        if search_type == "news":
            try:
                raw = await search_svc.search(
                    index="news",
                    query=q,
                    fields=_NEWS_FIELDS,
                    size=limit,
                    highlight=True,
                )
                results["news"] = _format_hits(raw, "news")
            except (OSError, ConnectionError):
                results["news"] = []

        elif search_type == "events":
            try:
                raw = await search_svc.search(
                    index="events",
                    query=q,
                    fields=_EVENTS_FIELDS,
                    size=limit,
                    highlight=True,
                )
                results["events"] = _format_hits(raw, "events")
            except (OSError, ConnectionError):
                results["events"] = []

    return {"query": q, "results": results}


def _format_hits(raw: dict[str, Any], result_type: str) -> list[dict[str, Any]]:
    """Format Elasticsearch hits into a clean frontend-friendly structure."""
    hits = raw.get("hits", [])
    formatted: list[dict[str, Any]] = []
    summary_field = "content" if result_type == "news" else "description"

    for hit in hits:
        source = hit.get("source", {})
        highlight = hit.get("highlights", {})
        formatted.append(
            {
                "id": hit.get("id", ""),
                "type": result_type,
                "title": source.get("title", ""),
                "summary": _get_highlight_or_field(highlight, source, summary_field),
                "score": hit.get("score", 0),
                "url": f"/{result_type}/{hit.get('id', '')}",
            }
        )

    return formatted


def _get_highlight_or_field(
    highlight: dict[str, Any],
    source: dict[str, Any],
    field: str,
) -> str:
    """Return highlighted snippet if available, else first 200 chars of field."""
    fragments = highlight.get(field, [])
    if fragments:
        return str(fragments[0])[:200]
    value = source.get(field, "")
    if isinstance(value, str):
        return value[:200]
    return ""
