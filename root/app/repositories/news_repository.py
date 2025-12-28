"""
News repository for news data access operations.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News
from app.repositories.base import BaseRepository


class NewsRepository(BaseRepository[News, dict, dict]):
    """Repository for News model operations."""

    @property
    def model(self) -> type[News]:
        return News

    async def get_published(
        self, *, skip: int = 0, limit: int = 20
    ) -> list[News]:
        """Get published news ordered by creation date descending."""
        result = await self.db.execute(
            select(News)
            .order_by(News.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest(self, limit: int = 5) -> list[News]:
        """Get the latest news items."""
        return await self.get_published(skip=0, limit=limit)

    async def search(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[News]:
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


def get_news_repository(db: AsyncSession) -> NewsRepository:
    """Factory function for dependency injection."""
    return NewsRepository(db)


__all__ = ["NewsRepository", "get_news_repository"]
