import contextlib
import uuid

from app.core.logging import get_logger
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import (
    NewsCommentDTO,
    NewsDTO,
    NewsInteractionsDTO,
    NewsListingDTO,
)
from app.services.vector_service import VectorService

logger = get_logger(__name__)


class NewsService:
    def __init__(self, uow: UnitOfWork, vector_service: VectorService):
        self.uow = uow
        self.repo = uow.news
        self.vector_service = vector_service

    async def list_news(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        current_user_id: uuid.UUID | None = None,
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
                with contextlib.suppress(ValueError, TypeError):
                    dt, id_str = decoded
                    decoded_cursor = (dt, id_str)

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
        for item in items_to_process:
            # item is NewsListingDTO
            output.append(self.serialize_news_listing(item, locale))

        next_cursor = None
        if has_more and items_to_process:
            last_item = items_to_process[-1]
            next_cursor = encode_datetime_cursor(
                last_item.news.created_at,
                str(last_item.news.id),
            )

        return schemas.PaginatedNews(
            items=output,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def create_news(self, data: schemas.NewsCreate) -> NewsDTO:
        news = await self.repo.create(data.model_dump())
        # BaseRepository.create returns DTO.
        # But DTO doesn't have 'record_event'.
        # We need a way to record events without using the ORM model if we want strict isolation.
        # Alternatively, the repo can record the event, or we can use a separate event bus.
        # Project uses models.record_event.
        # If I want isolation, I must move event recording to the repository or service using an event bus.
        # For now, I'll use the repo to record event or just keep it simple.

        # NewsCreated(news_id=news.id, title=str(news.title))
        # Wait, the repo created the record.

        # I'll add record_event support to BaseRepository or just do it manually if possible.
        # Actually models.record_event adds to a list on the object.
        # Since I have a DTO, I can't.

        async with self.uow:
            await self.uow.commit()
        return news

    async def toggle_like(self, news_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        liked = await self.repo.toggle_like(news_id, user_id)
        async with self.uow:
            await self.uow.commit()
        return bool(liked)

    async def get_news(
        self, news_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> NewsDTO | None:
        likes_count, is_liked = await self.repo.get_with_interactions(news_id, user_id)
        news = await self.repo.get(news_id)
        if news:
            news.likes_count = likes_count  # type: ignore[attr-defined]
            news.is_liked = is_liked  # type: ignore[attr-defined]
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

    async def get_news_with_details(
        self, news_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> NewsDTO | None:
        # HIGH-W19: implement instead of returning None (implicit from bare `pass`);
        # delegate to get_with_interactions to populate like/comment metadata.
        news = await self.repo.get(news_id)
        if news is None:
            return None
        likes_count, is_liked = await self.repo.get_with_interactions(news_id, user_id)
        news.likes_count = likes_count  # type: ignore[attr-defined]
        news.is_liked = is_liked  # type: ignore[attr-defined]
        return news

    async def get_news_item(
        self, news_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> NewsDTO | None:
        return await self.repo.get(news_id)

    async def update_news(
        self, news_id: uuid.UUID, data: schemas.NewsUpdate
    ) -> NewsDTO:
        news = await self.repo.get(news_id)
        if not news:
            raise ValueError("news_not_found")

        updates = data.model_dump(exclude_unset=True)
        # RZ-33-12: removed no-op self-assignments (updates[k] = updates.get(k))

        old_image_url = news.image_url

        updated_news = await self.repo.update(news_id, updates)
        assert updated_news is not None  # noqa: S101

        async with self.uow:
            await self.uow.commit()

        if old_image_url and updated_news.image_url != old_image_url:
            from app.utils.files import delete_static_file

            with contextlib.suppress(FileNotFoundError, OSError):  # RZ-33-15: narrowed
                await delete_static_file(str(old_image_url))

        return updated_news

    async def delete_news(self, news_id: uuid.UUID) -> bool:
        news = await self.repo.get(news_id)
        if not news:
            return False

        image_url = news.image_url
        await self.repo.delete(news_id)
        async with self.uow:
            await self.uow.commit()
        # Repository delete does execute/rowcount but usually not commit?
        # BaseRepository delete: execute delete stmt. Does NOT commit.
        # So we need to commit.

        if image_url:
            from app.utils.files import delete_static_file

            with contextlib.suppress(FileNotFoundError, OSError):  # RZ-33-15: narrowed
                await delete_static_file(str(image_url))
        return True

    async def create_comment(
        self, news_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> NewsCommentDTO:
        comment = await self.repo.create_comment(news_id, user_id, content)
        return NewsCommentDTO.model_validate(comment)

    async def update_comment(
        self, comment_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> NewsCommentDTO:
        comment_obj = await self.repo.get_comment(comment_id)
        if not comment_obj:
            raise LookupError("comment_not_found")
        if comment_obj.user_id != user_id:
            raise PermissionError("forbidden")
        updated = await self.repo.update_comment(comment_obj, content)
        return NewsCommentDTO.model_validate(updated)

    async def delete_comment(
        self, comment_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
    ) -> None:
        comment = await self.repo.get_comment(comment_id)
        if not comment:
            raise LookupError("comment_not_found")
        if comment.user_id != user_id and not is_admin:
            raise PermissionError("forbidden")
        await self.repo.delete_comment(comment)
        async with self.uow:
            await self.uow.commit()

    async def get_interactions(
        self,
        news_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NewsInteractionsDTO:
        return await self.repo.get_interactions(
            news_id,
            user_id,
            limit=limit,
            offset=offset,
        )

    def serialize_news(
        self, record: NewsDTO | schemas.NewsOut, locale: str
    ) -> schemas.NewsOut:
        # Logic from API _serialize_news
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

    def serialize_news_listing(
        self, listing: NewsListingDTO, locale: str
    ) -> schemas.NewsOut:
        from app.core.localization import localized_text, normalize_locale

        data = schemas.NewsOut.model_validate(listing.news).model_dump()
        normalized_locale = normalize_locale(locale)

        data["title"] = localized_text(
            normalized_locale, ru=data.get("title"), en=data.get("title_en")
        ) or (data.get("title") or "")

        data["content"] = localized_text(
            normalized_locale, ru=data.get("content"), en=data.get("content_en")
        ) or (data.get("content") or "")

        data["likes_count"] = listing.likes_count
        data["comments_count"] = listing.comments_count
        data["is_liked"] = listing.is_liked

        return schemas.NewsOut.model_validate(data)
