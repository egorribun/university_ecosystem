import contextlib
import uuid

from app.core.localization import localized_text, normalize_locale
from app.core.logging import get_logger
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import StoryDTO
from app.utils.files import delete_static_file

_logger = get_logger(__name__)


class StoryService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.repo = uow.stories

    def serialize_story(
        self,
        story: StoryDTO | schemas.StoryOut,
        locale: str | None,
    ) -> schemas.StoryOut:
        normalized_locale = normalize_locale(locale)
        story_out = (
            story
            if isinstance(story, schemas.StoryOut)
            else schemas.StoryOut.model_validate(story)
        )
        data = story_out.model_dump()
        data["title"] = localized_text(
            normalized_locale,
            ru=data.get("title"),
            en=data.get("title_en"),
        ) or (data.get("title") or "")
        data["short_text"] = localized_text(
            normalized_locale,
            ru=data.get("short_text"),
            en=data.get("short_text_en"),
        ) or (data.get("short_text") or "")
        return schemas.StoryOut.model_validate(data)

    async def list_active_stories(
        self, locale: str | None = None
    ) -> list[schemas.StoryOut]:
        rows = await self.repo.get_active(
            limit=100
        )  # Reasonable limit for active stories
        return [self.serialize_story(item, locale) for item in rows]

    async def create_story(
        self, data: schemas.StoryCreate, created_by: uuid.UUID
    ) -> StoryDTO:
        payload = data.model_dump(exclude_unset=True)

        if payload.get("published_at"):
            payload["published_at"] = self.repo._ensure_utc(payload["published_at"])
        if payload.get("expires_at"):
            payload["expires_at"] = self.repo._ensure_utc(payload["expires_at"])

        payload["created_by"] = created_by

        # We stick to repo.create if it fits, or manual add
        # Repo create assumes straight mapping, let's use it but might need overrides
        # BaseRepository.create takes dict or Pydantic.

        story = await self.repo.create(payload)
        async with self.uow:
            await self.uow.commit()
        return story

    async def update_story(
        self, story_id: uuid.UUID, data: schemas.StoryUpdate
    ) -> StoryDTO:
        story = await self.repo.get(story_id)
        if not story:
            raise ValueError("story_not_found")

        assert story is not None  # nosec B101

        old_cover = story.cover_url

        updates = data.model_dump(exclude_unset=True)

        if updates.get("published_at"):
            updates["published_at"] = self.repo._ensure_utc(updates["published_at"])
        if updates.get("expires_at"):
            updates["expires_at"] = self.repo._ensure_utc(updates["expires_at"])

        updated_story = await self.repo.update(story.id, updates)
        assert updated_story is not None  # nosec B101

        # Cleanup old cover if changed
        if old_cover and updated_story.cover_url != old_cover:
            try:
                await delete_static_file(str(old_cover))
            except Exception as exc:
                # Log but don't fail, similar to API logic
                _logger.debug("Failed to delete old story cover: %s", exc)  # nosec B110
                pass

        async with self.uow:
            await self.uow.commit()
        return updated_story

    async def delete_story(self, story_id: uuid.UUID) -> bool:
        story = await self.repo.get(story_id)
        if not story:
            return False

        cover_url = story.cover_url
        await self.repo.delete(story_id)
        async with self.uow:
            await self.uow.commit()

        if cover_url:
            with contextlib.suppress(Exception):
                await delete_static_file(str(cover_url))
        return True
