"""
News repository for news data access operations.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import and_, exists, false, func, or_, select

from app.core.cache import news_cache
from app.core.config import settings
from app.models import models
from app.models.news import News
from app.repositories.base import BaseRepository
from app.schemas.dtos import (
    NewsDTO,
    NewsInteractionsDTO,
    NewsListingDTO,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class NewsRepository(BaseRepository[News, NewsDTO, dict, dict]):
    """Repository for News model operations."""

    @property
    def model(self) -> type[News]:
        return News

    @property
    def dto_class(self) -> type[NewsDTO]:
        return NewsDTO

    async def get_published(self, *, skip: int = 0, limit: int = 20) -> list[NewsDTO]:
        """Get published news ordered by creation date descending with caching."""
        cache_key = f"news:published:{skip}:{limit}"
        cached = await news_cache.get(cache_key)
        if cached is not None:
            from typing import cast

            return cast(list[NewsDTO], cached)

        result = await self.db.execute(
            select(News).order_by(News.created_at.desc()).offset(skip).limit(limit)
        )
        news_items = list(result.scalars().all())
        dtos = [self._to_dto(obj) for obj in news_items]
        await news_cache.set(cache_key, dtos)
        return dtos

    async def get_latest(self, limit: int = 5) -> list[NewsDTO]:
        """Get the latest news items."""
        return await self.get_published(skip=0, limit=limit)

    async def search(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[NewsDTO]:
        """Search news by title (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(News)
            .where(func.lower(News.title).like(pattern))
            .order_by(News.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

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
    ) -> Sequence[NewsListingDTO]:
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
        rows = result.all()
        from app.schemas.dtos.news import NewsListingDTO

        return [
            NewsListingDTO(
                news=self._to_dto(row[0]),
                likes_count=row[1] or 0,
                comments_count=row[2] or 0,
                is_liked=bool(row[3]),
            )
            for row in rows
        ]

    async def get_with_interactions(
        self, news_id: uuid.UUID, current_user_id: uuid.UUID | None = None
    ):
        import asyncio

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

        likes_result, is_liked_result = await asyncio.gather(
            self.db.execute(likes_stmt), self.db.execute(is_liked_stmt)
        )

        likes_count = likes_result.scalar() or 0
        is_liked = is_liked_result.scalar() or False

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
        comment.content = content  # type: ignore[assignment]
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
    ) -> NewsInteractionsDTO:
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
            )  # type: ignore[call-overload]
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

        total_comments = (await self.db.execute(total_comments_stmt)).scalar() or 0

        from app.schemas.dtos.news import NewsCommentListingDTO, NewsInteractionsDTO

        return NewsInteractionsDTO(
            likes_count=likes_count,
            is_liked=is_liked,
            comments=[NewsCommentListingDTO.model_validate(c) for c in comments],
            comments_count=total_comments,
        )


def get_news_repository(db: AsyncSession) -> NewsRepository:
    """Factory function for dependency injection."""
    return NewsRepository(db)


__all__ = ["NewsRepository", "get_news_repository"]
