"""
News repository for news data access operations.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import models
from app.models.news import News
from app.repositories.base import BaseRepository


class NewsRepository(BaseRepository[News, dict, dict]):
    """Repository for News model operations."""

    @property
    def model(self) -> type[News]:
        return News

    async def get_published(self, *, skip: int = 0, limit: int = 20) -> list[News]:
        """Get published news ordered by creation date descending."""
        result = await self.db.execute(
            select(News).order_by(News.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest(self, limit: int = 5) -> list[News]:
        """Get the latest news items."""
        return await self.get_published(skip=0, limit=limit)

    async def search(self, query: str, *, skip: int = 0, limit: int = 20) -> list[News]:
        """Search news by title (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(News)
            .where(func.lower(News.title).like(pattern))
            .order_by(News.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_total(self) -> int:
        """Count total news items."""
        result = await self.db.execute(select(func.count(News.id)))
        return result.scalar() or 0

    async def list_news(
        self,
        *,
        limit: int = 20,
        cursor: tuple[datetime, int] | None = None,
        current_user_id: int | None = None,
        search_query: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> Sequence[tuple[News, int, int, bool]]:
        # Subqueries for counts
        likes_sub = (
            select(func.count(models.NewsLike.id))
            .where(models.NewsLike.news_id == News.id)
            .scalar_subquery()
            .label("likes_count")
        )
        comments_sub = (
            select(func.count(models.NewsComment.id))
            .where(models.NewsComment.news_id == News.id)
            .scalar_subquery()
            .label("comments_count")
        )

        is_liked_sub = (
            exists()
            .where(
                models.NewsLike.news_id == News.id,
                models.NewsLike.user_id == current_user_id,
            )
            .label("is_liked")
            if current_user_id
            else func.false().label("is_liked")
        )

        stmt = select(News, likes_sub, comments_sub, is_liked_sub)

        # Filters
        if cursor:
            last_created_at, last_id = cursor
            stmt = stmt.where(
                or_(
                    News.created_at < last_created_at,
                    and_(
                        News.created_at == last_created_at,
                        News.id < last_id,
                    ),
                )
            )

        rank_expr = None
        if search_query:
            if (
                settings.semantic_search_enabled
                and query_embedding
                and any(v != 0.0 for v in query_embedding)
            ):
                sim_score = 1.0 - News.embedding.cosine_distance(query_embedding)
                rank_expr = sim_score.label("sim_score")
                stmt = stmt.where(sim_score > 0.45)
            else:
                like = f"%{search_query}%"
                stmt = stmt.where(
                    or_(
                        News.title.ilike(like),
                        News.content.ilike(like),
                        News.title_en.ilike(like),
                        News.content_en.ilike(like),
                    )
                )

        if rank_expr is not None:
            stmt = stmt.order_by(
                rank_expr.desc(), News.created_at.desc(), News.id.desc()
            )
        else:
            stmt = stmt.order_by(News.created_at.desc(), News.id.desc())

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.all()

    async def get_with_interactions(
        self, news_id: int, current_user_id: int | None = None
    ):
        likes_stmt = select(func.count(models.NewsLike.id)).where(
            models.NewsLike.news_id == news_id
        )
        is_liked_stmt = (
            select(
                exists().where(
                    models.NewsLike.news_id == news_id,
                    models.NewsLike.user_id == current_user_id,
                )
            )
            if current_user_id
            else select(func.false())
        )

        likes_count = (await self.db.execute(likes_stmt)).scalar() or 0
        is_liked = (await self.db.execute(is_liked_stmt)).scalar() or False

        return likes_count, is_liked

    async def toggle_like(self, news_id: int, user_id: int) -> bool:
        stmt = select(models.NewsLike).where(
            models.NewsLike.news_id == news_id, models.NewsLike.user_id == user_id
        )
        result = await self.db.execute(stmt)
        like = result.scalar_one_or_none()
        if like:
            await self.db.delete(like)
            return False
        else:
            self.db.add(models.NewsLike(news_id=news_id, user_id=user_id))
            return True


def get_news_repository(db: AsyncSession) -> NewsRepository:
    """Factory function for dependency injection."""
    return NewsRepository(db)


__all__ = ["NewsRepository", "get_news_repository"]
