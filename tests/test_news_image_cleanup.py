from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import app.models as models
from app.api import news
from app.core.config import settings
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from tests.conftest import call_injected


@pytest.mark.asyncio
async def test_update_news_rejects_unowned_replacement_and_retains_legacy_file(
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

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))

    from app.services.news_service import NewsService

    # Mock vector service as we don't need embeddings here
    vector_service = MagicMock()
    vector_service.get_embedding = MagicMock()

    uow = uow_from_session(db_session)
    service = NewsService(uow, vector_service)

    payload = schemas.NewsUpdate(image_url="/static/news_images/new.png")

    with pytest.raises(HTTPException) as error:
        await call_injected(
            news.update_news,
            record.id,
            request=None,
            data=payload,
            user=admin,
            provides={"NewsService": service},
        )

    assert error.value.status_code == 403
    await db_session.refresh(record)
    assert record.image_url == "/static/news_images/old.png"
    assert old_path.exists()


@pytest.mark.asyncio
async def test_delete_news_retains_legacy_image_without_owner_key(
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

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))

    from app.services.news_service import NewsService

    # Mock vector service
    vector_service = MagicMock()
    uow = uow_from_session(db_session)
    service = NewsService(uow, vector_service)

    result = await call_injected(
        news.delete_news,
        record.id,
        request=None,
        user=admin,
        provides={"NewsService": service},
    )

    assert result == {"ok": True}
    assert await db_session.get(models.News, record.id) is None
    assert image_path.exists()
