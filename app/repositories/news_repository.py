"""
News repository for news data access operations.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, exists, false, func, or_, select

from app.core.cache import news_cache
from app.core.config import settings
from app.models import models
from app.models.news import News
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class NewsRepository(BaseRepository[News, dict, dict]):
    """Repository for News model operations."""

    @property
    def model(self) -> type[News]:
        return News

    async def get_published(self, *, skip: int = 0, limit: int = 20) -> list[News]:
        """Get published news ordered by creation date descending with caching."""
        cache_key = f"news:published:{skip}:{limit}"
        cached = await news_cache.get(cache_key)
        if cached is not None:
            return cached

        result = await self.db.execute(
            select(News).order_by(News.created_at.desc()).offset(skip).limit(limit)
        )
        news_items = list(result.scalars().all())
        await news_cache.set(cache_key, news_items)
        return news_items

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
        cursor: tuple[datetime, uuid.UUID | str] | None = None,
        current_user_id: uuid.UUID | str | None = None,
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

        if current_user_id and isinstance(current_user_id, str):
            with contextlib.suppress(ValueError):
                current_user_id = uuid.UUID(current_user_id)

        is_liked_sub = (
            exists()
            .where(
                models.NewsLike.news_id == News.id,
                models.NewsLike.user_id == current_user_id,
            )
            .label("is_liked")
            if current_user_id
            else false().label("is_liked")
        )

        stmt = select(News, likes_sub, comments_sub, is_liked_sub)

        # Filters
        if cursor:
            last_created_at, last_id = cursor
            if isinstance(last_id, str):
                with contextlib.suppress(ValueError):
                    last_id = uuid.UUID(last_id)
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
                and any(abs(v) > 1e-9 for v in query_embedding)
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
        self, news_id: uuid.UUID, current_user_id: uuid.UUID | None = None
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

    async def toggle_like(self, news_id: uuid.UUID, user_id: uuid.UUID) -> bool:
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

    async def get_comment(self, comment_id: uuid.UUID) -> models.NewsComment | None:
        """Get a comment by ID."""
        return await self.db.get(models.NewsComment, comment_id)

    async def create_comment(
        self, news_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> models.NewsComment:
        """Create a new comment."""
        comment = models.NewsComment(news_id=news_id, user_id=user_id, content=content)
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment, ["user"])
        return comment

    async def update_comment(
        self, comment: models.NewsComment, content: str
    ) -> models.NewsComment:
        """Update a comment."""
        comment.content = content
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment, ["user"])
        return comment

    async def delete_comment(self, comment: models.NewsComment) -> None:
        """Delete a comment."""
        await self.db.delete(comment)

    async def get_interactions(
        self,
        news_id: uuid.UUID,
        current_user_id: uuid.UUID | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get likes count, current user's like status, and comments for a news item."""
        # Count likes
        likes_stmt = select(func.count(models.NewsLike.id)).where(
            models.NewsLike.news_id == news_id
        )
        likes_result = await self.db.execute(likes_stmt)
        likes_count = likes_result.scalar() or 0

        # User like status
        is_liked = False
        if current_user_id:
            liked_stmt = select(models.NewsLike.id).where(
                models.NewsLike.news_id == news_id,
                models.NewsLike.user_id == current_user_id,
            )
            is_liked = (await self.db.execute(liked_stmt)).scalar() is not None

        # Get comments with user names (paginated)
        comments_stmt = (
            select(
                models.NewsComment.id,
                models.NewsComment.content,
                models.NewsComment.user_id,
                models.User.full_name,
                models.NewsComment.created_at,
            )
            .join(models.User, models.NewsComment.user_id == models.User.id)
            .where(models.NewsComment.news_id == news_id)
            .order_by(models.NewsComment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        comments_result = await self.db.execute(comments_stmt)
        comments = [
            {
                "id": row[0],
                "content": row[1],
                "user_id": row[2],
                "user_name": row[3],
                "created_at": row[4],
            }
            for row in comments_result.all()
        ]

        # Total comments count
        total_comments_stmt = select(func.count(models.NewsComment.id)).where(
            models.NewsComment.news_id == news_id
        )
        total_comments = (await self.db.execute(total_comments_stmt)).scalar() or 0

        return {
            "likes_count": likes_count,
            "is_liked": is_liked,
            "comments": comments,
            "comments_count": total_comments,
        }


def get_news_repository(db: AsyncSession) -> NewsRepository:
    """Factory function for dependency injection."""
    return NewsRepository(db)


__all__ = ["NewsRepository", "get_news_repository"]
