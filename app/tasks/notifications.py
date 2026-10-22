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


def _normalize_task_uuid(value: uuid.UUID | int | str) -> uuid.UUID:
    """Restore UUID-valued IDs after JSON transport while keeping legacy ints."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, int):
        return uuid.UUID(int=value)
    return uuid.UUID(value)


@broker.task()
async def enqueue_news_notification_task(
    news_id: uuid.UUID | int | str,
    locale: str | None = None,
) -> None:
    """Distributed task for sending news notifications."""
    news_id = _normalize_task_uuid(news_id)
    async with async_session() as db:
        news = await db.get(News, news_id)
        if news:
            await _notify_about_news(db, news, locale=locale)
            await db.commit()


@broker.task()
async def enqueue_event_notification_task(
    event_id: uuid.UUID | int | str,
    locale: str | None = None,
) -> None:
    """Distributed task for sending event notifications."""
    event_id = _normalize_task_uuid(event_id)
    async with async_session() as db:
        event = await db.get(Event, event_id)
        if event:
            await _notify_about_event(db, event, locale=locale)
            await db.commit()


@broker.task()
async def enqueue_comment_notification_task(
    news_id: uuid.UUID | int | str,
    comment_id: uuid.UUID | int | str,
    user_id: uuid.UUID | int | str,
    locale: str | None = None,
) -> None:
    """Distributed task for sending comment notifications to admins."""
    news_id = _normalize_task_uuid(news_id)
    comment_id = _normalize_task_uuid(comment_id)
    user_id = _normalize_task_uuid(user_id)
    async with async_session() as db:
        news = await db.get(News, news_id)
        comment = await db.get(NewsComment, comment_id)
        author = await db.get(User, user_id)

        if news and comment and author:
            await _notify_about_comment(db, news, comment, author, locale=locale)
            await db.commit()
