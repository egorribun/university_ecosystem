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

from typing import Any

from app.core.logging import get_logger

# RZ-W8-02: Hard caps to prevent deep-pagination DoS (O(from+size) in Elasticsearch).
_MAX_SEARCH_SIZE = 100
_MAX_SEARCH_OFFSET = 10_000

# RZ-W8-03: Non-HTML sentinel delimiters for search highlights.
# The frontend MUST escape the surrounding text before replacing these sentinels
# with <mark> tags.  Using raw HTML tags ("pre_tags": ["<mark>"]) lets stored XSS
# pass through if Elasticsearch doesn't escape document content.
_HIGHLIGHT_OPEN = "\x00MARK_OPEN\x00"
_HIGHLIGHT_CLOSE = "\x00MARK_CLOSE\x00"

from elasticsearch import (  # noqa: E402
    ApiError,
    AsyncElasticsearch,
    TransportError,
)
from elasticsearch.helpers import (  # noqa: E402
    async_bulk,
)

logger = get_logger(__name__)


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

    async def publish_rebuilt_indices(self, replacements: dict[str, str]) -> None:
        """Atomically expose complete rebuilds, including legacy concrete names."""
        actions: list[dict[str, Any]] = []
        obsolete: list[str] = []
        for name, replacement in replacements.items():
            if await self.client.indices.exists_alias(name=name):
                aliases = await self.client.indices.get_alias(name=name)
                for previous in aliases:
                    actions.append(
                        {
                            "remove": {
                                "index": previous,
                                "alias": name,
                                "must_exist": True,
                            }
                        }
                    )
                    if previous.startswith(f"{name}-rebuild-"):
                        obsolete.append(previous)
            elif await self.client.indices.exists(index=name):
                actions.append({"remove_index": {"index": name}})
            actions.append(
                {"add": {"index": replacement, "alias": name, "is_write_index": True}}
            )
        await self.client.indices.refresh(index=",".join(replacements.values()))
        result = await self.client.indices.update_aliases(actions=actions)
        if result.get("errors") or not result.get("acknowledged"):
            raise RuntimeError("Search alias publication was not confirmed")
        # Publication has succeeded. Cleanup failure must not make callers delete
        # the now-live replacement or report that the atomic switch failed.
        for previous in obsolete:
            try:
                await self.delete_index(previous)
            except (OSError, ConnectionError, TimeoutError, TransportError, ApiError):
                logger.warning("Unable to clean obsolete search index %s", previous)

    async def delete_index(self, index: str) -> None:
        """Remove an index owned by a rebuild (not a public read/write alias)."""
        await self.client.indices.delete(index=index, ignore_unavailable=True)

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

        def generate_actions() -> Generator[dict[str, Any]]:
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
        fields: list[str],
        size: int = 20,
        offset: int = 0,
        highlight: bool = True,
    ) -> dict[str, Any]:
        """Perform a full-text search.

        Args:
            index: Index name
            query: Search query string
            fields: Fields to search — REQUIRED; passing ["*"] exposes internal
                    metadata fields to user-controlled queries.
            size: Maximum results to return (capped at _MAX_SEARCH_SIZE)
            offset: Result offset for pagination (capped at _MAX_SEARCH_OFFSET)
            highlight: Whether to include highlights

        Returns:
            Search results with hits and metadata
        """
        # RZ-W8-02: Clamp size/offset to prevent deep-pagination DoS.
        # Also truncate query string to prevent excessively long fuzzy expansions.
        size = min(max(1, size), _MAX_SEARCH_SIZE)
        offset = min(max(0, offset), _MAX_SEARCH_OFFSET)
        query = query[:256]

        # TD-W8-05: Require explicit field list — wildcard ["*"] accidentally
        # exposes all indexed fields including internal metadata to user queries.
        if not fields:
            raise ValueError(
                "search() requires an explicit 'fields' list. "
                "An empty list is not allowed; pass the fields relevant to the index "
                "(e.g. ['title', 'content'] for news, ['title', 'description'] for events)."
            )

        search_body: dict[str, Any] = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": fields,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "size": size,
            "from": offset,
        }

        if highlight:
            # RZ-W8-03: Use non-HTML sentinel delimiters — Elasticsearch does not
            # HTML-escape surrounding content, so raw <mark> tags create a stored
            # XSS vector if the frontend renders highlights via innerHTML.
            # The frontend must HTML-escape text first, then replace sentinels.
            search_body["highlight"] = {
                "fields": {field: {} for field in fields},
                "pre_tags": [_HIGHLIGHT_OPEN],
                "post_tags": [_HIGHLIGHT_CLOSE],
                "number_of_fragments": 3,
                "fragment_size": 150,
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
            size: Maximum suggestions (capped at 20)

        Returns:
            List of suggested terms
        """
        # LOW-W19: cap suggestion count to prevent callers from requesting
        # arbitrarily large completion payloads, which can exhaust heap memory
        # in Elasticsearch for high-cardinality completion fields.
        size = min(size, 20)

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
        "title_en": {"type": "text", "analyzer": "english"},
        "content": {"type": "text", "analyzer": "russian"},
        "content_en": {"type": "text", "analyzer": "english"},
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
        "title_en": {"type": "text", "analyzer": "english"},
        "description": {"type": "text", "analyzer": "russian"},
        "description_en": {"type": "text", "analyzer": "english"},
        "location": {"type": "text"},
        "organizer_name": {"type": "keyword"},
        "start_time": {"type": "date"},
        "end_time": {"type": "date"},
        "category": {"type": "keyword"},
    }
}
__all__ = [
    "EVENTS_MAPPINGS",
    "NEWS_MAPPINGS",
    "SearchService",
]
