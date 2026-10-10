from __future__ import annotations

import math
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.core.ssrf import validate_url_not_internal_async

logger = get_logger(__name__)


class SemanticSearchUnavailableError(RuntimeError):
    """Raised when semantic search cannot obtain a usable embedding."""


SEMANTIC_SEARCH_UNAVAILABLE_DETAIL = "Semantic search is currently unavailable"


# LOW-W19: metric counter for embedding provider failures. Uses a simple
# in-process counter as a lightweight default; replace with a Prometheus
# Counter or OTLP metric where a metrics exporter is configured.
_embedding_failure_count: int = 0


def _inc_embedding_failure() -> None:
    """Increment the embedding-failure counter and log the running total."""
    global _embedding_failure_count
    _embedding_failure_count += 1
    logger.warning(
        "Embedding provider failures (total this process: %d)",
        _embedding_failure_count,
    )


class VectorService:
    """Service for handling embeddings and semantic search."""

    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db
        self._base_url = settings.embedding_api_base
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"}
            if settings.embedding_api_key
            else {},
            timeout=10.0,
        )

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for a given text using the configured provider."""
        if not settings.semantic_search_enabled:
            raise SemanticSearchUnavailableError(SEMANTIC_SEARCH_UNAVAILABLE_DETAIL)

        if not settings.embedding_api_key:
            logger.warning("Embedding API key is not configured")
            raise SemanticSearchUnavailableError(SEMANTIC_SEARCH_UNAVAILABLE_DETAIL)

        # Validate only when used, before transmitting the API key or input.
        # Keep security rejection outside the provider-error conversion.
        await validate_url_not_internal_async(self._base_url)
        try:
            response = await self._client.post(
                "/embeddings", json={"input": text, "model": settings.embedding_model}
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            if (
                not isinstance(embedding, list)
                or not embedding
                or len(embedding) != settings.embedding_dimensions
                or not all(
                    type(value) in (int, float) and math.isfinite(value)
                    for value in embedding
                )
                or not any(embedding)
            ):
                raise ValueError("Embedding provider returned an unusable vector")
            return [float(value) for value in embedding]
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            OverflowError,
            KeyError,
            IndexError,
            TypeError,
            httpx.HTTPStatusError,
            httpx.TransportError,
        ) as err:
            # RZ-20-04 + RZ-33-04: httpx.HTTPStatusError added for raise_for_status().
            logger.warning(
                "Embedding provider request failed",
                error_type=type(err).__name__,
            )
            _inc_embedding_failure()
            raise SemanticSearchUnavailableError(
                SEMANTIC_SEARCH_UNAVAILABLE_DETAIL
            ) from None

    async def search_similar_with_scores(
        self,
        model: Any,
        embedding: list[float],
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[tuple[Any, float]]:
        """
        Perform a semantic search and return results with their scores.
        Scores are normalized (1.0 = perfect match, 0.0 = no similarity).
        """
        if not settings.semantic_search_enabled or not embedding:
            return []

        # pgvector cosine_distance is 1 - cosine_similarity
        # similarity is what we usually call 'score'
        distance = model.embedding.cosine_distance(embedding)
        score = (1.0 - distance).label("similarity_score")

        stmt = select(model, score).where(score >= min_score)

        if hasattr(model, "is_active"):
            stmt = stmt.where(model.is_active == True)  # noqa: E712
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))

        stmt = stmt.order_by(score.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def search_similar(
        self, model: Any, embedding: list[float], limit: int = 5, min_score: float = 0.5
    ) -> list[Any]:
        """Perform a simple semantic search using cosine similarity."""
        results = await self.search_similar_with_scores(
            model, embedding, limit=limit, min_score=min_score
        )
        return [r[0] for r in results]

    async def close(self) -> None:
        await self._client.aclose()

    # MED-W19: expose as async context manager so callers can guarantee the
    # underlying httpx.AsyncClient is closed even on exception paths.
    async def __aenter__(self) -> VectorService:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
