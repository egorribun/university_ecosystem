import logging

from app.core.events import NewsCreated
from app.models import models
from app.repositories.news import NewsRepository
from app.schemas import schemas
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, repo: NewsRepository, vector_service: VectorService):
        self.repo = repo
        self.vector_service = vector_service

    async def list_news(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        current_user_id: int | None = None,
        search: str | None = None,
    ):
        query_embedding = None
        if search:
            query_embedding = await self.vector_service.get_embedding(search)

        decoded_cursor = None  # cursor decoding logic...

        return await self.repo.list_news(
            limit=limit,
            cursor=decoded_cursor,
            current_user_id=current_user_id,
            search_query=search,
            query_embedding=query_embedding,
        )

    async def create_news(self, data: schemas.NewsCreate) -> models.News:
        news = await self.repo.create(**data.model_dump())
        news.record_event(NewsCreated(news_id=news.id, title=news.title))
        await self.repo.db.commit()
        await self.repo.db.refresh(news)
        return news

    async def toggle_like(self, news_id: int, user_id: int) -> bool:
        liked = await self.repo.toggle_like(news_id, user_id)
        await self.repo.db.commit()
        return liked
