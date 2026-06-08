import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import schemas
from app.schemas.dtos import StoryDTO
from app.services.story_service import StoryService


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.stories = AsyncMock()
    return uow


@pytest.mark.asyncio
async def test_serialize_story_model_dump_locale_en(mock_uow):
    service = StoryService(mock_uow)
    now = datetime.datetime.now(datetime.UTC)
    story_dto = MagicMock(spec=StoryDTO)
    story_dto.id = uuid.uuid4()
    story_dto.title = "Русский заголовок"
    story_dto.title_en = "English Title"
    story_dto.short_text = "Русский текст"
    story_dto.short_text_en = "English text"
    story_dto.cover_url = "http://example.com/cover.jpg"
    story_dto.cta_url = None
    story_dto.is_active = True
    story_dto.published_at = now
    story_dto.expires_at = now
    story_dto.created_at = now
    story_dto.created_by = uuid.uuid4()
    story_dto.cover_url_optimized = None

    # Pass DTO and locale='en'
    res = service.serialize_story(story_dto, locale="en")
    assert res.title == "English Title"
    assert res.short_text == "English text"


@pytest.mark.asyncio
async def test_serialize_story_model_dump_locale_ru(mock_uow):
    service = StoryService(mock_uow)
    now = datetime.datetime.now(datetime.UTC)
    story_out = schemas.StoryOut(
        id=uuid.uuid4(),
        title="Русский заголовок",
        title_en="English Title",
        short_text="Русский текст",
        short_text_en="English text",
        cover_url="http://example.com/cover.jpg",
        is_active=True,
        published_at=now,
        expires_at=now,
        created_at=now,
        created_by=uuid.uuid4(),
    )

    # Pass StoryOut directly and locale='ru'
    res = service.serialize_story(story_out, locale="ru")
    assert res.title == "Русский заголовок"
    assert res.short_text == "Русский текст"


@pytest.mark.asyncio
async def test_list_active_stories(mock_uow):
    service = StoryService(mock_uow)
    now = datetime.datetime.now(datetime.UTC)
    mock_item = MagicMock()
    mock_item.id = uuid.uuid4()
    mock_item.title = "Title"
    mock_item.title_en = "Title EN"
    mock_item.short_text = "Text"
    mock_item.short_text_en = "Text EN"
    mock_item.cover_url = None
    mock_item.cta_url = None
    mock_item.is_active = True
    mock_item.published_at = now
    mock_item.expires_at = now
    mock_item.created_at = now
    mock_item.created_by = uuid.uuid4()
    mock_item.cover_url_optimized = None

    mock_uow.stories.get_active.return_value = [mock_item]

    res = await service.list_active_stories(locale="en")
    assert len(res) == 1
    assert res[0].title == "Title EN"
    mock_uow.stories.get_active.assert_awaited_once_with(limit=100)


@pytest.mark.asyncio
async def test_create_story(mock_uow):
    service = StoryService(mock_uow)
    now = datetime.datetime.now(datetime.UTC)
    data = schemas.StoryCreate(
        title="New Story",
        short_text="Context",
        published_at=now,
        expires_at=now + datetime.timedelta(days=1),
        is_active=True,
    )
    user_id = uuid.uuid4()

    # Stub timezone conversion in repo
    mock_uow.stories._ensure_utc = lambda x: x

    await service.create_story(data, user_id)
    mock_uow.stories.create.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_story_not_found(mock_uow):
    service = StoryService(mock_uow)
    mock_uow.stories.get.return_value = None
    data = schemas.StoryUpdate(title="Updated Title")

    with pytest.raises(ValueError, match="story_not_found"):
        await service.update_story(uuid.uuid4(), data)


@pytest.mark.asyncio
async def test_update_story_success_with_cover_change(mock_uow):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)

    old_story = MagicMock()
    old_story.id = story_id
    old_story.cover_url = "old_cover.jpg"
    mock_uow.stories.get.return_value = old_story

    new_story = MagicMock()
    new_story.id = story_id
    new_story.cover_url = "new_cover.jpg"
    mock_uow.stories.update.return_value = new_story
    mock_uow.stories._ensure_utc = lambda x: x

    data = schemas.StoryUpdate(
        title="Updated Title",
        published_at=now,
        expires_at=now + datetime.timedelta(days=1),
        cover_url="new_cover.jpg",
    )

    with patch(
        "app.services.story_service.delete_static_file", new_callable=AsyncMock
    ) as mock_delete:
        res = await service.update_story(story_id, data)
        assert res == new_story
        mock_uow.stories.update.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()
        mock_delete.assert_awaited_once_with("old_cover.jpg")


@pytest.mark.asyncio
async def test_update_story_success_delete_cover_fail_ignored(mock_uow):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()

    old_story = MagicMock()
    old_story.id = story_id
    old_story.cover_url = "old_cover.jpg"
    mock_uow.stories.get.return_value = old_story

    new_story = MagicMock()
    new_story.id = story_id
    new_story.cover_url = "new_cover.jpg"
    mock_uow.stories.update.return_value = new_story

    data = schemas.StoryUpdate(cover_url="new_cover.jpg")

    with patch(
        "app.services.story_service.delete_static_file",
        side_effect=OSError("disk failure"),
    ) as mock_delete:
        res = await service.update_story(story_id, data)
        assert res == new_story
        # Verify it does not propagate error
        mock_delete.assert_awaited_once_with("old_cover.jpg")


@pytest.mark.asyncio
async def test_delete_story_not_found(mock_uow):
    service = StoryService(mock_uow)
    mock_uow.stories.get.return_value = None

    res = await service.delete_story(uuid.uuid4())
    assert res is False


@pytest.mark.asyncio
async def test_delete_story_success_with_cover(mock_uow):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()

    story = MagicMock()
    story.id = story_id
    story.cover_url = "cover.jpg"
    mock_uow.stories.get.return_value = story

    with patch(
        "app.services.story_service.delete_static_file", new_callable=AsyncMock
    ) as mock_delete:
        res = await service.delete_story(story_id)
        assert res is True
        mock_uow.stories.delete.assert_awaited_once_with(story_id)
        mock_uow.commit.assert_awaited_once()
        mock_delete.assert_awaited_once_with("cover.jpg")
