"""Elasticsearch search service for full-text search.

This module provides an async Elasticsearch client for indexing and
searching content like news, events, and chat messages.

Features:
- Async operations with AsyncElasticsearch
- Full-text search with relevance scoring
- Bulk indexing for efficient imports
- Auto-suggest and highlighting
"""

from __future__ import annotations

import logging
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

logger = logging.getLogger(__name__)


class SearchService:
    """Async Elasticsearch service for full-text search."""

    def __init__(
        self,
        hosts: list[str] | str = "http://localhost:9200",
        http_auth: tuple[str, str] | None = None,
    ) -> None:
        self._hosts = [hosts] if isinstance(hosts, str) else hosts
        self._http_auth = http_auth
        self._client: AsyncElasticsearch | None = None

    @property
    def client(self) -> AsyncElasticsearch:
        if self._client is None:
            kwargs: dict[str, Any] = {"hosts": self._hosts}
            if self._http_auth is not None:
                kwargs["http_auth"] = self._http_auth
            self._client = AsyncElasticsearch(**kwargs)
        return self._client

    async def close(self) -> None:
        """Close the Elasticsearch connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def ensure_index(
        self,
        index: str,
        mappings: dict[str, Any] | None = None,
    ) -> None:
        """Create an index if it doesn't exist.

        Args:
            index: Index name
            mappings: Optional field mappings
        """
        exists = await self.client.indices.exists(index=index)
        if not exists:
            body = {}
            if mappings:
                body["mappings"] = mappings
            await self.client.indices.create(index=index, body=body)
            logger.info("Created index: %s", index)

    async def index_document(
        self,
        index: str,
        document_id: str,
        body: dict[str, Any],
    ) -> None:
        """Index a single document.

        Args:
            index: Index name
            document_id: Document ID
            body: Document content
        """
        await self.client.index(index=index, id=document_id, body=body)
        logger.debug("Indexed document %s in %s", document_id, index)

    async def bulk_index(
        self,
        index: str,
        documents: list[dict[str, Any]],
        id_field: str = "id",
    ) -> tuple[int, int]:
        """Bulk index multiple documents.

        Args:
            index: Index name
            documents: List of documents to index
            id_field: Field to use as document ID

        Returns:
            Tuple of (success_count, failed_count)
        """

        from collections.abc import Generator

        def generate_actions() -> Generator[dict[str, Any], None, None]:
            for doc in documents:
                yield {
                    "_index": index,
                    "_id": doc.get(id_field),
                    "_source": doc,
                }

        success, failed = await async_bulk(
            self.client,
            generate_actions(),
            raise_on_error=False,
        )
        failed_count = len(failed) if isinstance(failed, list) else failed
        logger.info("Bulk indexed %d documents, %d failed", success, failed_count)
        return success, failed_count

    async def search(
        self,
        index: str,
        query: str,
        fields: list[str] | None = None,
        size: int = 20,
        offset: int = 0,
        highlight: bool = True,
    ) -> dict[str, Any]:
        """Perform a full-text search.

        Args:
            index: Index name
            query: Search query string
            fields: Fields to search (default: all text fields)
            size: Maximum results to return
            offset: Result offset for pagination
            highlight: Whether to include highlights

        Returns:
            Search results with hits and metadata
        """
        search_body: dict[str, Any] = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": fields or ["*"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "size": size,
            "from": offset,
        }

        if highlight:
            search_body["highlight"] = {
                "fields": {"*": {}},
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            }

        result = await self.client.search(index=index, body=search_body)

        return {
            "total": result["hits"]["total"]["value"],
            "hits": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"],
                    "highlights": hit.get("highlight", {}),
                }
                for hit in result["hits"]["hits"]
            ],
        }

    async def suggest(
        self,
        index: str,
        query: str,
        field: str = "title",
        size: int = 5,
    ) -> list[str]:
        """Get search suggestions (autocomplete).

        Args:
            index: Index name
            query: Partial query string
            field: Field to suggest from
            size: Maximum suggestions

        Returns:
            List of suggested terms
        """
        result = await self.client.search(
            index=index,
            body={
                "suggest": {
                    "suggestions": {
                        "prefix": query,
                        "completion": {
                            "field": f"{field}.suggest",
                            "size": size,
                            "skip_duplicates": True,
                        },
                    }
                }
            },
        )

        suggestions = result.get("suggest", {}).get("suggestions", [])
        if suggestions and suggestions[0].get("options"):
            return [opt["text"] for opt in suggestions[0]["options"]]
        return []

    async def delete_document(
        self,
        index: str,
        document_id: str,
    ) -> None:
        """Delete a document from the index.

        Args:
            index: Index name
            document_id: Document ID to delete
        """
        import elasticsearch

        try:
            await self.client.delete(index=index, id=document_id)
        except elasticsearch.NotFoundError:
            pass
        logger.debug("Deleted document %s from %s", document_id, index)


# Index mappings for university ecosystem
NEWS_MAPPINGS = {
    "properties": {
        "title": {
            "type": "text",
            "analyzer": "russian",
            "fields": {"suggest": {"type": "completion"}},
        },
        "content": {"type": "text", "analyzer": "russian"},
        "summary": {"type": "text", "analyzer": "russian"},
        "author_name": {"type": "keyword"},
        "created_at": {"type": "date"},
        "tags": {"type": "keyword"},
    }
}

EVENTS_MAPPINGS = {
    "properties": {
        "title": {
            "type": "text",
            "analyzer": "russian",
            "fields": {"suggest": {"type": "completion"}},
        },
        "description": {"type": "text", "analyzer": "russian"},
        "location": {"type": "text"},
        "organizer_name": {"type": "keyword"},
        "start_time": {"type": "date"},
        "end_time": {"type": "date"},
        "category": {"type": "keyword"},
    }
}


# Singleton instance
_search_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Get the configured search service instance."""
    global _search_service
    if _search_service is None:
        from app.core.config import settings

        hosts = getattr(settings, "elasticsearch_url", "http://localhost:9200")
        user = getattr(settings, "elasticsearch_user", "elastic")
        password = getattr(settings, "elasticsearch_password", "")
        http_auth: tuple[str, str] | None = (user, password) if password else None
        _search_service = SearchService(hosts=hosts, http_auth=http_auth)
    return _search_service


__all__ = [
    "EVENTS_MAPPINGS",
    "NEWS_MAPPINGS",
    "SearchService",
    "get_search_service",
]
