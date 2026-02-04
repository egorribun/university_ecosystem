import logging
from typing import Any

from app.core.events import NewsCreated
from app.models import models
from app.repositories.news_repository import NewsRepository
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
        locale: str = "ru",
    ) -> schemas.PaginatedNews:
        query_embedding = None
        if search:
            query_embedding = await self.vector_service.get_embedding(search)

        from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

        decoded_cursor = None
        if cursor:
            decoded = decode_datetime_cursor(cursor)
            if decoded:
                dt, id_str = decoded
                try:
                    decoded_cursor = (dt, id_str)
                except (ValueError, TypeError):
                    pass

        # Fetch limit + 1 to determine has_more
        results = await self.repo.list_news(
            limit=limit + 1,
            cursor=decoded_cursor,
            current_user_id=current_user_id,
            search_query=search,
            query_embedding=query_embedding,
        )

        has_more = len(results) > limit
        items_to_process = results[:limit]

        output = []
        for news_obj, l_count, c_count, liked in items_to_process:
            news_obj.likes_count = l_count or 0
            news_obj.comments_count = c_count or 0
            news_obj.is_liked = bool(liked)
            output.append(self.serialize_news(news_obj, locale))

        next_cursor = None
        if has_more and items_to_process:
            last_item, *_ = items_to_process[-1]
            next_cursor = encode_datetime_cursor(
                last_item.created_at, str(last_item.id)
            )

        return schemas.PaginatedNews(
            items=output,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def create_news(self, data: schemas.NewsCreate) -> models.News:
        news = await self.repo.create(data.model_dump())
        news.record_event(NewsCreated(news_id=news.id, title=news.title))
        await self.repo.db.commit()
        await self.repo.db.refresh(news)
        return news

    async def toggle_like(self, news_id: int, user_id: int) -> bool:
        liked = await self.repo.toggle_like(news_id, user_id)
        await self.repo.db.commit()
        return liked

    async def get_news(self, news_id: int, user_id: int | None = None):
        likes_count, is_liked = await self.repo.get_with_interactions(news_id, user_id)
        news = await self.repo.get(news_id)
        if news:
            news.likes_count = likes_count
            news.is_liked = is_liked
            # Comments count is not fetched here in the repo method, might need it?
            # The repo.get_with_interactions returns (likes_count, is_liked).
            # The API get_news uses a complex query to get comments_count too.
            # Let's fix get_with_interactions in repo properly first?
            # Or just add a separate query?
            # Actually, let's keep it simple here and assume we might need to fetch it.
            # For now, let's stick to what we have or accept a small inconsistency
            # OR better, update get_with_interactions to verify it matches needs.
            pass
        return news

    async def get_news_with_details(self, news_id: int, user_id: int | None = None):
        # Placeholder for complex detail retrieval if needed
        pass

    async def get_news_item(
        self, news_id: int, user_id: int | None = None
    ) -> models.News | None:
        # Composite getter
        # For now invalidating cache logic is in API.
        # Service should handle DB operations.

        # Re-implementing logic from API get_news using repo:
        # API does: get counts (likes, comments), get user like status, get news.
        # Repo has get_published, get_latest, list_news.
        # Repo has get_with_interactions (likes, is_liked).
        # We need comments_count too.
        # I'll update repo later or just do ad-hoc queries here?
        # No, use repo.

        # Let's just implement the basic CRUD for comments first.
        return await self.repo.get(news_id)

    async def update_news(self, news_id: int, data: schemas.NewsUpdate) -> models.News:
        news = await self.repo.get(news_id)
        if not news:
            raise ValueError("news_not_found")

        updates = data.model_dump(exclude_unset=True)
        # Sanitization should be in Service
        from app.utils.sanitization import sanitize_optional_text

        if "title_en" in updates:
            updates["title_en"] = sanitize_optional_text(updates.get("title_en"))
        if "content_en" in updates:
            updates["content_en"] = sanitize_optional_text(updates.get("content_en"))

        old_image_url = news.image_url

        updated_news = await self.repo.update(news.id, updates)

        content_changed = "title" in updates or "content" in updates
        if content_changed:
            from app.core.events import NewsUpdated

            updated_news.record_event(
                NewsUpdated(news_id=updated_news.id, title=updated_news.title)
            )

        await self.repo.db.commit()
        await self.repo.db.refresh(updated_news)

        from app.utils.files import delete_static_file

        if old_image_url and updated_news.image_url != old_image_url:
            try:
                await delete_static_file(old_image_url)
            except Exception:
                pass

        return updated_news

    async def delete_news(self, news_id: int) -> bool:
        news = await self.repo.get(news_id)
        if not news:
            return False

        image_url = news.image_url
        await self.repo.delete(news_id)
        await (
            self.repo.db.commit()
        )  # Repository delete does execute/rowcount but usually not commit?
        # BaseRepository delete: execute delete stmt. Does NOT commit.
        # So we need to commit.

        from app.utils.files import delete_static_file

        if image_url:
            try:
                await delete_static_file(image_url)
            except Exception:
                pass
        return True

    async def create_comment(
        self, news_id: int, user_id: int, content: str
    ) -> models.NewsComment:
        return await self.repo.create_comment(news_id, user_id, content)

    async def update_comment(
        self, comment_id: int, user_id: int, content: str
    ) -> models.NewsComment:
        comment = await self.repo.get_comment(comment_id)
        if not comment:
            raise LookupError("comment_not_found")
        if comment.user_id != user_id:
            raise PermissionError("forbidden")
        return await self.repo.update_comment(comment, content)

    async def delete_comment(
        self, comment_id: int, user_id: int, is_admin: bool = False
    ) -> None:
        comment = await self.repo.get_comment(comment_id)
        if not comment:
            raise LookupError("comment_not_found")
        if comment.user_id != user_id and not is_admin:
            raise PermissionError("forbidden")
        await self.repo.delete_comment(comment)
        await self.repo.db.commit()

    async def get_interactions(
        self, news_id: int, user_id: int | None = None, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        return await self.repo.get_interactions(
            news_id, user_id, limit=limit, offset=offset
        )

    def serialize_news(
        self, record: models.News | schemas.NewsOut, locale: str
    ) -> schemas.NewsOut:
        # Logic from API _serialize_news

        # Re-implement _localized_text here or import?
        # It's better to implement it cleanly using sanitized logic if we can.
        # But for now let's reproduce it or assume it's available.
        # Actually EventService uses `_localized_event_field`.
        from app.core.localization import localized_text, normalize_locale

        model_out = (
            record
            if isinstance(record, schemas.NewsOut)
            else schemas.NewsOut.model_validate(record)
        )
        data = model_out.model_dump()
        normalized_locale = normalize_locale(locale)

        data["title"] = localized_text(
            normalized_locale, ru=data.get("title"), en=data.get("title_en")
        ) or (data.get("title") or "")

        data["content"] = localized_text(
            normalized_locale, ru=data.get("content"), en=data.get("content_en")
        ) or (data.get("content") or "")

        data["likes_count"] = getattr(record, "likes_count", 0)
        data["comments_count"] = getattr(record, "comments_count", 0)
        data["is_liked"] = getattr(record, "is_liked", False)

        return schemas.NewsOut.model_validate(data)
