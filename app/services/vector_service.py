import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncDatabaseSession

logger = logging.getLogger(__name__)


class VectorService:
    """Service for handling embeddings and semantic search."""

    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db
        self._client = httpx.AsyncClient(
            base_url=settings.embedding_api_base,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"}
            if settings.embedding_api_key
            else {},
            timeout=10.0,
        )

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for a given text using the configured provider."""
        if not settings.semantic_search_enabled:
            return [0.0] * settings.embedding_dimensions

        if not settings.embedding_api_key:
            logger.warning("Embedding API key not set, returning zero vector")
            return [0.0] * settings.embedding_dimensions

        try:
            response = await self._client.post(
                "/embeddings", json={"input": text, "model": settings.embedding_model}
            )
            response.raise_for_status()
            data = response.json()
            from typing import cast

            return cast("list[float]", data["data"][0]["embedding"])
        except Exception:
            logger.exception("Failed to fetch embedding")
            return [0.0] * settings.embedding_dimensions

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

        stmt = (
            select(model, score)
            .where(score >= min_score)
            .order_by(score.desc())
            .limit(limit)
        )
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

    async def close(self):
        await self._client.aclose()
