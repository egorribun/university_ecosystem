import pytest

from app.api import news
from app.core.config import settings
from app.models import models
from app.schemas import schemas


@pytest.mark.anyio("asyncio")
async def test_update_news_removes_replaced_image(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    record = models.News(
        title="Title", content="Body", image_url="/static/news_images/old.png"
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    old_path = tmp_path / "news_images" / "old.png"
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"old")

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    payload = schemas.NewsCreate(
        title=record.title,
        content=record.content,
        image_url="/static/news_images/new.png",
    )

    updated = await news.update_news(
        record.id, payload, request=None, db=db_session, user=admin
    )

    assert updated.image_url == "/static/news_images/new.png"
    assert not old_path.exists()


@pytest.mark.anyio("asyncio")
async def test_delete_news_removes_image_file(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    record = models.News(
        title="Title", content="Body", image_url="/static/news_images/old.png"
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    image_path = tmp_path / "news_images" / "old.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"payload")

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    result = await news.delete_news(
        record.id, request=None, db=db_session, user=admin
    )

    assert result == {"ok": True}
    assert await db_session.get(models.News, record.id) is None
    assert not image_path.exists()
