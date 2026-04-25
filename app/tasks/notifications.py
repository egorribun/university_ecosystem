import uuid

from app.core.database import async_session
from app.core.nats_broker import broker
from app.models import Event, News, NewsComment, User
from app.services.notifications.news_events import (
    notify_about_comment as _notify_about_comment,
)
from app.services.notifications.news_events import (
    notify_about_event as _notify_about_event,
)
from app.services.notifications.news_events import (
    notify_about_news as _notify_about_news,
)


@broker.task()
async def enqueue_news_notification_task(
    news_id: uuid.UUID,
    locale: str | None = None,
) -> None:
    """Distributed task for sending news notifications."""
    async with async_session() as db:
        news = await db.get(News, news_id)
        if news:
            await _notify_about_news(db, news, locale=locale)
            await db.commit()


@broker.task()
async def enqueue_event_notification_task(
    event_id: uuid.UUID,
    locale: str | None = None,
) -> None:
    """Distributed task for sending event notifications."""
    async with async_session() as db:
        event = await db.get(Event, event_id)
        if event:
            await _notify_about_event(db, event, locale=locale)
            await db.commit()


@broker.task()
async def enqueue_comment_notification_task(
    news_id: uuid.UUID | int,
    comment_id: uuid.UUID | int,
    user_id: uuid.UUID | int,
    locale: str | None = None,
) -> None:
    """Distributed task for sending comment notifications to admins."""
    async with async_session() as db:
        news = await db.get(News, news_id)
        comment = await db.get(NewsComment, comment_id)
        author = await db.get(User, user_id)

        if news and comment and author:
            await _notify_about_comment(db, news, comment, author, locale=locale)
            await db.commit()
