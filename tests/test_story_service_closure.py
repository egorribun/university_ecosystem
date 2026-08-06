"""Branch closure tests for StoryService optional timestamp and cover paths."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas import schemas
from app.services.story_service import StoryService


def _service():
    uow = AsyncMock()
    uow.stories = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    uow.stories._ensure_utc = MagicMock(side_effect=lambda value: value)
    return StoryService(uow), uow


@pytest.mark.asyncio
async def test_create_story_without_optional_timestamps():
    service, uow = _service()
    uow.stories.create.return_value = MagicMock()

    await service.create_story(
        schemas.StoryCreate(title="Title", short_text="Text"), uuid4()
    )

    uow.stories._ensure_utc.assert_not_called()
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_story_without_old_cover_skips_file_cleanup():
    service, uow = _service()
    story = MagicMock(id=uuid4(), cover_url=None)
    updated = MagicMock(cover_url=None)
    uow.stories.get.return_value = story
    uow.stories.update.return_value = updated

    assert (
        await service.update_story(story.id, schemas.StoryUpdate(title="new"))
        is updated
    )


@pytest.mark.asyncio
async def test_delete_story_without_cover_skips_file_cleanup():
    service, uow = _service()
    story = MagicMock(cover_url=None)
    uow.stories.get.return_value = story

    assert await service.delete_story(uuid4()) is True
    uow.commit.assert_awaited_once()
