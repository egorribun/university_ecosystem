from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select

from app.core.config import settings
from app.models import models
from app.repositories.base import BaseRepository


class NewsRepository(BaseRepository[models.News]):
    def __init__(self, db):
        super().__init__(models.News, db)

    async def list_news(
        self,
        *,
        limit: int = 20,
        cursor: tuple[datetime, int] | None = None,
        current_user_id: int | None = None,
        search_query: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> Sequence[tuple[models.News, int, int, bool]]:
        # Subqueries for counts
        likes_sub = (
            select(func.count(models.NewsLike.id))
            .where(models.NewsLike.news_id == models.News.id)
            .scalar_subquery()
            .label("likes_count")
        )
        comments_sub = (
            select(func.count(models.NewsComment.id))
            .where(models.NewsComment.news_id == models.News.id)
            .scalar_subquery()
            .label("comments_count")
        )

        is_liked_sub = (
            exists()
            .where(
                models.NewsLike.news_id == models.News.id,
                models.NewsLike.user_id == current_user_id,
            )
            .label("is_liked")
            if current_user_id
            else func.false().label("is_liked")
        )

        stmt = select(models.News, likes_sub, comments_sub, is_liked_sub)

        # Filters
        if cursor:
            last_created_at, last_id = cursor
            stmt = stmt.where(
                or_(
                    models.News.created_at < last_created_at,
                    and_(
                        models.News.created_at == last_created_at,
                        models.News.id < last_id,
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
                sim_score = 1.0 - models.News.embedding.cosine_distance(query_embedding)
                rank_expr = sim_score.label("sim_score")
                stmt = stmt.where(sim_score > 0.45)
            else:
                like = f"%{search_query}%"
                stmt = stmt.where(
                    or_(
                        models.News.title.ilike(like),
                        models.News.content.ilike(like),
                        models.News.title_en.ilike(like),
                        models.News.content_en.ilike(like),
                    )
                )

        if rank_expr is not None:
            stmt = stmt.order_by(
                rank_expr.desc(), models.News.created_at.desc(), models.News.id.desc()
            )
        else:
            stmt = stmt.order_by(models.News.created_at.desc(), models.News.id.desc())

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
