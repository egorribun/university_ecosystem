from app.core.database import async_session
from app.core.tkq import broker
from app.models.models import Event, News
from app.services.notifications.news_events import (
    notify_about_event as _notify_about_event,
)
from app.services.notifications.news_events import (
    notify_about_news as _notify_about_news,
)


@broker.task
async def enqueue_news_notification_task(
    news_id: int,
    locale: str | None = None,
) -> None:
    """Distributed task for sending news notifications."""
    async with async_session() as db:
        news = await db.get(News, news_id)
        if news:
            await _notify_about_news(db, news, locale=locale)
            await db.commit()


@broker.task
async def enqueue_event_notification_task(
    event_id: int,
    locale: str | None = None,
) -> None:
    """Distributed task for sending event notifications."""
    async with async_session() as db:
        event = await db.get(Event, event_id)
        if event:
            await _notify_about_event(db, event, locale=locale)
            await db.commit()
