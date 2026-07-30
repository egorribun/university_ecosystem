"""
News repository for news data access operations.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import selectinload

import app.models as models
from app.core.cache import cached, news_cache
from app.core.config import settings
from app.core.protocols import AsyncDatabaseSession
from app.core.tenant import get_current_tenant
from app.models.news import News
from app.repositories.base import BaseRepository
from app.schemas.dtos import (
    NewsDTO,
    NewsInteractionsDTO,
    NewsListingDTO,
)
from app.schemas.dtos.news import NewsCommentListingDTO

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from app.core.protocols import AsyncDatabaseSession


def build_news_cache_key(self: Any, *, skip: int = 0, limit: int = 20) -> str:
    tenant_id = get_current_tenant() or "public"
    return f"news:published:{tenant_id}:{skip}:{limit}"


class NewsRepository(BaseRepository[News, NewsDTO, dict[str, Any], dict[str, Any]]):
    """Repository for News model operations."""

    def __init__(self, db: AsyncDatabaseSession):
        super().__init__(db)

    @property
    def model(self) -> type[News]:
        return News

    @property
    def dto_class(self) -> type[NewsDTO]:
        return NewsDTO

    @cached(cache_instance=news_cache, key_builder=build_news_cache_key)
    async def get_published(self, *, skip: int = 0, limit: int = 20) -> list[NewsDTO]:
        """Get published news ordered by creation date descending with caching."""
        # TODO: News model has no is_published column; all news rows are treated as published.
        # Add a published: Mapped[bool] column to News when drafts are required.
        result = await self.db.execute(
            select(News)
            .options(selectinload(News.author))
            .order_by(News.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        news_items = list(result.scalars().all())
        dtos = [self._to_dto(obj) for obj in news_items]
        return dtos

    async def get_latest(self, limit: int = 5) -> list[NewsDTO]:
        """Get the latest news items."""
        return cast(list[NewsDTO], await self.get_published(skip=0, limit=limit))

    async def search(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[NewsDTO]:
        """Search news by title (case-insensitive)."""
        # CRIT-01 (audit 2026-03-11): Escape LIKE wildcards before embedding.
        safe_query = self._escape_like(query.strip().lower())
        pattern = f"%{safe_query}%"
        result = await self.db.execute(
            select(News)
            .options(selectinload(News.author))
            .where(func.lower(News.title).like(pattern, escape="\\"))
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
        """
        List news items with aggregate counts (likes, comments) and user's like status.
        Optimized to avoid scalar subqueries by using batch fetching.
        """
        if current_user_id:
            current_user_id = self._cast_id(current_user_id)

        # 1. Fetch news objects with pagination/cursor/search
        stmt = select(News).options(selectinload(News.author))

        if cursor:
            last_created_at, last_id = cursor
            last_id = self._cast_id(last_id)
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
                # PERF-01 Fix: Use ORDER BY distance LIMIT N instead of distance-based filter.
                # This ensures pgvector HNSW/IVFFlat indexes are utilized for ANN search.
                # Distance-based filters (WHERE dist < X) trigger a full table scan in many PG versions.
                rank_expr = News.embedding.cosine_distance(query_embedding).label(
                    "vector_dist"
                )
            else:
                stmt = stmt.where(
                    or_(
                        News.title.bool_op("%")(search_query),
                        News.content.bool_op("%")(search_query),
                        News.title_en.bool_op("%")(search_query),
                        News.content_en.bool_op("%")(search_query),
                    )
                )

        if rank_expr is not None:
            # TD-003: pgvector HNSW indexes require strict ORDER BY distance LIMIT N.
            # Adding other columns to ORDER BY (like created_at) breaks the index
            # and forces a full sequential scan + sort.
            stmt = stmt.order_by(rank_expr.asc())
        else:
            stmt = stmt.order_by(News.created_at.desc(), News.id.desc())

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        news_items = result.scalars().all()

        if not news_items:
            return []

        news_ids = [item.id for item in news_items]

        # 2. Batch fetch likes and comments counts
        # Using a single query with LEFT JOIN and GROUP BY is possible, but
        # multiple aggregate joins can lead to Cartesian product issues if not careful.
        # Batching via subqueries or separate grouped selects is often cleaner.

        likes_stmt = (
            select(models.NewsLike.news_id, func.count(models.NewsLike.id))
            .where(models.NewsLike.news_id.in_(news_ids))
            .group_by(models.NewsLike.news_id)
        )
        comments_stmt = (
            select(models.NewsComment.news_id, func.count(models.NewsComment.id))
            .where(models.NewsComment.news_id.in_(news_ids))
            .group_by(models.NewsComment.news_id)
        )

        # RZ-W19-04: AsyncSession is NOT concurrency-safe — sequential queries required
        likes_res = await self.db.execute(likes_stmt)
        comments_res = await self.db.execute(comments_stmt)

        likes_map = {row[0]: row[1] for row in likes_res.all()}
        comments_map = {row[0]: row[1] for row in comments_res.all()}

        # 3. Batch fetch current user's like status
        is_liked_map = {}
        if current_user_id:
            liked_stmt = select(models.NewsLike.news_id).where(
                models.NewsLike.news_id.in_(news_ids),
                models.NewsLike.user_id == current_user_id,
            )
            liked_res = await self.db.execute(liked_stmt)
            is_liked_map = {news_id: True for (news_id,) in liked_res.all()}

        # 4. Assemble DTOs
        from app.schemas.dtos.news import NewsListingDTO

        return [
            NewsListingDTO(
                news=self._to_dto(item),
                likes_count=likes_map.get(item.id, 0),
                comments_count=comments_map.get(item.id, 0),
                is_liked=is_liked_map.get(item.id, False),
            )
            for item in news_items
        ]

    async def get_with_interactions(
        self, news_id: uuid.UUID, current_user_id: uuid.UUID | None = None
    ) -> tuple[int, bool]:
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

        # RZ-W19-04: AsyncSession is NOT concurrency-safe — sequential queries required
        likes_result = await self.db.execute(likes_stmt)
        is_liked_result = await self.db.execute(is_liked_stmt)

        likes_count = likes_result.scalar() or 0
        is_liked = is_liked_result.scalar() or False

        return likes_count, is_liked

    async def toggle_like(self, news_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Atomic toggle like operation using Postgres-native Upsert."""
        from sqlalchemy.dialects.postgresql import insert

        # RZ-004 Fix: Avoid SELECT ... FOR UPDATE on non-existent rows.
        # Use INSERT ON CONFLICT DO NOTHING for atomic seat-taking.
        stmt = (
            insert(models.NewsLike)
            .values(news_id=news_id, user_id=user_id)
            .on_conflict_do_nothing()
        )
        result = await self.db.execute(stmt)

        if result.rowcount == 0:  # type: ignore[attr-defined]
            # Row existed, so this is a 'remove like' action.
            from sqlalchemy import delete

            del_stmt = delete(models.NewsLike).where(
                models.NewsLike.news_id == news_id, models.NewsLike.user_id == user_id
            )
            await self.db.execute(del_stmt)
            return False

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
    ) -> NewsInteractionsDTO:
        """Get likes count, current user's like status, and comments for a news item."""
        likes_stmt = select(func.count(models.NewsLike.id)).where(
            models.NewsLike.news_id == news_id
        )
        comments_stmt = (
            select(
                models.NewsComment.id,
                models.NewsComment.content,
                models.NewsComment.user_id,
                func.coalesce(models.UserProfile.full_name, models.User.email),
                models.NewsComment.created_at,
            )
            .join(models.User, models.NewsComment.user_id == models.User.id)
            .outerjoin(models.UserProfile, models.User.id == models.UserProfile.user_id)
            .where(models.NewsComment.news_id == news_id)
            .order_by(models.NewsComment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        total_comments_stmt = select(func.count(models.NewsComment.id)).where(
            models.NewsComment.news_id == news_id
        )

        # RZ-W19-04: AsyncSession is NOT concurrency-safe — sequential queries required
        likes_res = await self.db.execute(likes_stmt)
        comments_res = await self.db.execute(comments_stmt)
        total_res = await self.db.execute(total_comments_stmt)

        likes_count = likes_res.scalar() or 0
        total_comments = total_res.scalar() or 0
        comments = [
            {
                "id": row[0],
                "content": row[1],
                "user_id": row[2],
                "user_name": row[3],
                "created_at": row[4],
            }
            for row in comments_res.all()
        ]

        is_liked = False
        if current_user_id:
            liked_stmt = select(models.NewsLike.id).where(
                models.NewsLike.news_id == news_id,
                models.NewsLike.user_id == current_user_id,
            )
            is_liked = (await self.db.execute(liked_stmt)).scalar() is not None

        return NewsInteractionsDTO(
            likes_count=likes_count,
            is_liked=is_liked,
            comments=[NewsCommentListingDTO.model_validate(c) for c in comments],
            comments_count=total_comments,
        )

    async def get_analytics_data(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> tuple[Sequence[Any], Sequence[str]]:
        """Fetch raw news data for high-performance Polars analytics."""
        likes_count = func.count(func.distinct(models.NewsLike.id)).label("likes_count")
        comments_count = func.count(func.distinct(models.NewsComment.id)).label(
            "comments_count"
        )

        stmt = (
            select(
                models.News.id,
                models.News.title,
                models.News.created_at,
                likes_count,
                comments_count,
                func.date_trunc("day", models.News.created_at).label("date"),
            )
            .outerjoin(models.NewsLike, models.NewsLike.news_id == models.News.id)
            .outerjoin(models.NewsComment, models.NewsComment.news_id == models.News.id)
            .group_by(models.News.id)
        )
        if start_date:
            stmt = stmt.where(models.News.created_at >= start_date)
        if end_date:
            stmt = stmt.where(models.News.created_at <= end_date)

        result = await self.db.execute(stmt)
        return result.fetchall(), list(result.keys())


def get_news_repository(db: AsyncDatabaseSession) -> NewsRepository:
    """Factory function for dependency injection."""
    return NewsRepository(db)


__all__ = ["NewsRepository", "get_news_repository"]
