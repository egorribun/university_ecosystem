from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.notifications.news_events import notify_about_event, notify_about_news


@pytest.mark.asyncio
async def test_notify_about_news_logic():
    db = AsyncMock()
    news = MagicMock()
    news.id = 1
    news.title = "Test Title"
    news.content = "Test Content"

    with (
        patch(
            "app.services.notifications.news_events.resolve_locale", return_value="en"
        ),
        patch(
            "app.services.notifications.news_events.render_notification_template",
            return_value={"title": "T", "body": "B"},
        ),
        patch(
            "app.services.notifications.news_events._fetch_active_user_ids",
            new_callable=AsyncMock,
            return_value=[uuid4()],
        ),
        patch(
            "app.services.notifications.news_events.create_notifications_for_users",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        result = await notify_about_news(db, news)
        assert result == 1


@pytest.mark.asyncio
async def test_notify_about_event_logic():
    db = AsyncMock()
    event = MagicMock()
    event.id = str(uuid4())
    event.title = "Event Name"
    event.description = "Event Description"
    event.starts_at = datetime.now(UTC)

    with (
        patch(
            "app.services.notifications.news_events.normalize_locale", return_value="en"
        ),
        patch(
            "app.services.notifications.news_events.render_notification_template",
            return_value={"title": "ET", "body": "EB"},
        ),
        patch(
            "app.services.notifications.news_events._fetch_active_user_ids",
            new_callable=AsyncMock,
            return_value=[uuid4()],
        ),
        patch(
            "app.services.notifications.news_events.create_notifications_for_users",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        result = await notify_about_event(db, event)
        assert result == 1
