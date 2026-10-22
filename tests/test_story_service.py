import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import schemas
from app.schemas.dtos import StoryDTO
from app.services.story_service import StoryService


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.stories = AsyncMock()
    return uow


def _install_storage_delete_spy(monkeypatch):
    from app.utils import files

    backend = MagicMock()
    backend.delete_file = AsyncMock()
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    return backend


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
async def test_update_story_success_with_cover_change(mock_uow, monkeypatch):
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

    backend = _install_storage_delete_spy(monkeypatch)
    res = await service.update_story(story_id, data)
    assert res == new_story
    mock_uow.stories.update.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    backend.delete_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_story_retains_legacy_cover_without_storage_call(
    mock_uow, monkeypatch
):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()

    old_story = MagicMock()
    old_story.id = story_id
    old_story.cover_url = "/static/news_images/legacy-cover.png"
    mock_uow.stories.get.return_value = old_story

    new_story = MagicMock()
    new_story.id = story_id
    new_story.cover_url = "new_cover.jpg"
    mock_uow.stories.update.return_value = new_story

    data = schemas.StoryUpdate(cover_url="new_cover.jpg")
    backend = _install_storage_delete_spy(monkeypatch)
    res = await service.update_story(story_id, data)

    assert res == new_story
    mock_uow.stories.update.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    backend.delete_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_story_not_found(mock_uow):
    service = StoryService(mock_uow)
    mock_uow.stories.get.return_value = None

    res = await service.delete_story(uuid.uuid4())
    assert res is False


@pytest.mark.asyncio
async def test_delete_story_preserves_row_crud_and_never_deletes_cover(
    mock_uow, monkeypatch
):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()

    story = MagicMock()
    story.id = story_id
    story.cover_url = "/static/avatars/profile-cover.png"
    mock_uow.stories.get.return_value = story

    backend = _install_storage_delete_spy(monkeypatch)
    res = await service.delete_story(story_id)

    assert res is True
    mock_uow.stories.delete.assert_awaited_once_with(story_id)
    mock_uow.commit.assert_awaited_once()
    backend.delete_file.assert_not_awaited()


@pytest.mark.parametrize(
    "cover_url",
    [
        "https://images.example.test/external-cover.png",
        "/static/avatars/user_00000000000000000000000000000000_cover_"
        "11111111111111111111111111111111.png",
        "/static/tmp/event_images/event_00000000-0000-0000-0000-000000000000_"
        "22222222222222222222222222222222.jpg",
        "/static/news_images/news_33333333333333333333333333333333.webp",
        "/static/story_covers/legacy-cover.png",
        "../../avatars/other.png",
        "http://[invalid",
    ],
)
@pytest.mark.asyncio
async def test_delete_story_never_deletes_foreign_or_legacy_cover_urls(
    mock_uow, monkeypatch, cover_url
):
    service = StoryService(mock_uow)
    story_id = uuid.uuid4()
    mock_uow.stories.get.return_value = MagicMock(id=story_id, cover_url=cover_url)
    backend = _install_storage_delete_spy(monkeypatch)

    assert await service.delete_story(story_id) is True
    mock_uow.stories.delete.assert_awaited_once_with(story_id)
    mock_uow.commit.assert_awaited_once()
    backend.delete_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_shared_story_cover_retains_file_for_other_story(
    tmp_path, monkeypatch, db_session, story_factory
):
    from app.repositories.unit_of_work import uow_from_session
    from app.services.storage import StaticFSStorage
    from app.utils import files

    key = f"story_covers/stories_{uuid.uuid4().hex}.png"
    cover_url = f"/static/{key}"
    cover_path = tmp_path.joinpath(*key.split("/"))
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"shared story cover")
    first = await story_factory(cover_url=cover_url)
    other = await story_factory(cover_url=cover_url)
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)

    service = StoryService(uow_from_session(db_session))
    new_url = "https://images.example.test/replacement.png"
    updated = await service.update_story(
        first.id, schemas.StoryUpdate(cover_url=new_url)
    )

    assert updated.cover_url == new_url
    await db_session.refresh(other)
    assert other.cover_url == cover_url
    assert cover_path.exists()


@pytest.mark.asyncio
async def test_delete_shared_story_cover_retains_file_for_other_story(
    tmp_path, monkeypatch, db_session, story_factory
):
    from app.models import Story
    from app.repositories.unit_of_work import uow_from_session
    from app.services.storage import StaticFSStorage
    from app.utils import files

    key = f"story_covers/stories_{uuid.uuid4().hex}.jpg"
    cover_url = f"/static/{key}"
    cover_path = tmp_path.joinpath(*key.split("/"))
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"shared story cover")
    first = await story_factory(cover_url=cover_url)
    other = await story_factory(cover_url=cover_url)
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)

    service = StoryService(uow_from_session(db_session))
    assert await service.delete_story(first.id) is True

    assert await db_session.get(Story, first.id) is None
    remaining = await db_session.get(Story, other.id)
    assert remaining is not None
    assert remaining.cover_url == cover_url
    assert cover_path.exists()


@pytest.mark.asyncio
async def test_story_cover_remains_when_update_commit_rolls_back(
    tmp_path, monkeypatch, db_session, story_factory
):
    from app.repositories.unit_of_work import uow_from_session
    from app.services.storage import StaticFSStorage
    from app.utils import files

    key = f"story_covers/stories_{uuid.uuid4().hex}.jpg"
    cover_url = f"/static/{key}"
    cover_path = tmp_path.joinpath(*key.split("/"))
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"story cover")
    story = await story_factory(cover_url=cover_url)
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    uow = uow_from_session(db_session)
    service = StoryService(uow)

    async def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(uow, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await service.update_story(
            story.id, schemas.StoryUpdate(cover_url="new-cover.png")
        )

    await db_session.refresh(story)
    assert story.cover_url == cover_url
    assert cover_path.exists()
