import re
import uuid
from datetime import UTC, datetime, timedelta

from app.core.localization import localized_text, normalize_locale
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import StoryDTO
from app.services.news_media import canonical_upload_key

# The key ``POST /stories/upload_cover`` generates (save_upload "story_covers",
# prefix "stories"). Covers load from the site itself: img-src allows no other
# image host apart from Spotify album art (ADR-047).
_STORY_COVER_KEY = re.compile(
    r"story_covers/stories_[0-9a-f]{32}\.(?:jpg|png|webp)", flags=re.ASCII
)


class InvalidStoryPeriod(ValueError):
    """The effective publication interval is missing or nonpositive."""


class StoryCoverNotUploaded(ValueError):
    """A new cover URL is not a canonical story cover upload."""


def _require_uploaded_cover(cover_url: str | None) -> None:
    if cover_url and canonical_upload_key(cover_url, _STORY_COVER_KEY) is None:
        raise StoryCoverNotUploaded("story_cover_not_uploaded")


def _validate_story_period(
    published_at: datetime | None, expires_at: datetime | None
) -> None:
    if published_at is None or expires_at is None:
        raise InvalidStoryPeriod("story_period_invalid")
    # SQLite removes timezone metadata; compare instants using the same UTC
    # interpretation as the input schemas and repository.
    published = (
        published_at.replace(tzinfo=UTC)
        if published_at.tzinfo is None
        else published_at.astimezone(UTC)
    )
    expires = (
        expires_at.replace(tzinfo=UTC)
        if expires_at.tzinfo is None
        else expires_at.astimezone(UTC)
    )
    if expires <= published:
        raise InvalidStoryPeriod("story_period_invalid")


class StoryService:
    """Story operations retain covers until exclusive ownership is verifiable."""

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
        _require_uploaded_cover(payload.get("cover_url"))
        published_at = data.published_at or datetime.now(UTC)
        try:
            expires_at = data.expires_at or published_at + timedelta(hours=24)
        except OverflowError as exc:
            raise InvalidStoryPeriod("story_period_invalid") from exc
        _validate_story_period(published_at, expires_at)
        payload["published_at"] = published_at
        payload["expires_at"] = expires_at
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
        updates = data.model_dump(exclude_unset=True)
        async with self.uow:
            changes_time = bool({"published_at", "expires_at"} & updates.keys())
            story = (
                await self.repo.get_for_time_update(story_id)
                if changes_time
                else await self.repo.get(story_id)
            )
            if story is None:
                raise ValueError("story_not_found")
            if "cover_url" in updates and updates["cover_url"] != story.cover_url:
                # An unchanged cover may predate this rule; only new ones must
                # be uploads.
                _require_uploaded_cover(updates.get("cover_url"))
            if changes_time:
                _validate_story_period(
                    updates.get("published_at", story.published_at),
                    updates.get("expires_at", story.expires_at),
                )
            updated_story = await self.repo.update(story.id, updates)
            assert updated_story is not None  # noqa: S101
            await self.uow.commit()

        # Cover URLs can be shared across story rows. Retain the prior object
        # because this row alone cannot prove exclusive ownership.

        return updated_story

    async def delete_story(self, story_id: uuid.UUID) -> bool:
        story = await self.repo.get(story_id)
        if not story:
            return False

        await self.repo.delete(story_id)
        async with self.uow:
            await self.uow.commit()

        return True
