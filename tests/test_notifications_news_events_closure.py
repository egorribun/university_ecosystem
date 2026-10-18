from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.notifications import news_events


def _news(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "title": "Заголовок",
        "title_en": "Headline",
        "content": "Подробное содержание новости",
        "content_en": "Detailed news content",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _event(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "title": "Событие",
        "title_en": "Event",
        "description": "Описание",
        "description_en": "Description",
        "about": "О событии",
        "about_en": "About event",
        "location": "Аудитория 1",
        "location_en": "Room 1",
        "event_type": "Лекция",
        "event_type_en": "Lecture",
        "speaker": "Speaker",
        "starts_at": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_news_default_template_and_empty_audience_paths() -> None:
    news = _news(
        id=None,
        title=None,
        title_en=None,
        content=None,
        content_en="   ",
    )
    with (
        patch.object(
            news_events,
            "resolve_locale",
            side_effect=lambda locale=None: locale or "ru",
        ),
        patch.object(news_events, "render_notification_template", return_value=None),
        patch.object(news_events, "translate", return_value=""),
        patch.object(news_events, "_fetch_active_user_ids", AsyncMock(return_value=[])),
    ):
        result = await news_events.notify_about_news(AsyncMock(), news, locale=None)
    assert result == 0


@pytest.mark.asyncio
async def test_news_template_data_and_payload_filtering() -> None:
    news = _news(id=None, title="  ", title_en=None, content="Summary", content_en=None)
    create = AsyncMock(return_value=4)
    template = {
        "title": "Template title",
        "body": "Template body",
        "url": "",
        "tag": "",
        "data": ["not-a-mapping"],
    }
    with (
        patch.object(news_events, "resolve_locale", return_value="en"),
        patch.object(
            news_events, "render_notification_template", return_value=template
        ),
        patch.object(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(
            news_events,
            "_unnotified_user_ids",
            AsyncMock(side_effect=lambda _db, _key, candidate_ids: candidate_ids),
        ),
        patch.object(news_events, "create_notifications_for_users", create),
    ):
        result = await news_events.notify_about_news(AsyncMock(), news, locale="en")
    assert result == 4
    assert create.await_args.kwargs["url"] == "/news"
    assert create.await_args.kwargs["tag"] == "news"
    assert create.await_args.kwargs["payload_data"]["category"] == "news"
    assert create.await_args.kwargs["payload_data"]["summary"] == "Summary"


@pytest.mark.asyncio
async def test_event_default_template_covers_optional_details() -> None:
    event = _event(
        id=None,
        title=None,
        title_en=None,
        description=None,
        description_en=None,
        about=None,
        about_en=None,
        location=None,
        location_en=None,
        event_type=None,
        event_type_en=None,
        speaker=None,
        starts_at=datetime.now(),
    )
    create = AsyncMock(return_value=2)
    with (
        patch.object(news_events, "normalize_locale", return_value="en"),
        patch.object(news_events, "render_notification_template", return_value=None),
        patch.object(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(
            news_events,
            "_unnotified_user_ids",
            AsyncMock(side_effect=lambda _db, _key, candidate_ids: candidate_ids),
        ),
        patch.object(news_events, "create_notifications_for_users", create),
    ):
        result = await news_events.notify_about_event(AsyncMock(), event, locale="en")
    assert result == 2
    assert create.await_args.kwargs["url"] == "/events"
    assert create.await_args.kwargs["tag"] == "event"


@pytest.mark.asyncio
async def test_event_template_mapping_and_empty_audience() -> None:
    event = _event()
    template = {
        "title": "Template event",
        "body": "Template body",
        "url": "/custom-event",
        "tag": "custom-tag",
        "data": {"custom": "value"},
    }
    create = AsyncMock(return_value=3)
    with (
        patch.object(news_events, "normalize_locale", return_value="ru"),
        patch.object(
            news_events, "render_notification_template", return_value=template
        ),
        patch.object(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(
            news_events,
            "_unnotified_user_ids",
            AsyncMock(side_effect=lambda _db, _key, candidate_ids: candidate_ids),
        ),
        patch.object(news_events, "create_notifications_for_users", create),
    ):
        result = await news_events.notify_about_event(AsyncMock(), event, locale="ru")
    assert result == 3
    assert create.await_args.kwargs["url"] == "/custom-event"
    assert create.await_args.kwargs["payload_data"]["custom"] == "value"

    with (
        patch.object(news_events, "normalize_locale", return_value="ru"),
        patch.object(news_events, "render_notification_template", return_value=None),
        patch.object(news_events, "_fetch_active_user_ids", AsyncMock(return_value=[])),
    ):
        assert await news_events.notify_about_event(AsyncMock(), event) == 0

    empty_template = {"title": "", "body": "", "url": "", "tag": ""}
    with (
        patch.object(news_events, "normalize_locale", return_value="ru"),
        patch.object(
            news_events,
            "render_notification_template",
            return_value=empty_template,
        ),
        patch.object(news_events, "translate", return_value=""),
        patch.object(news_events, "_fetch_active_user_ids", AsyncMock(return_value=[])),
    ):
        assert await news_events.notify_about_event(AsyncMock(), event) == 0


@pytest.mark.asyncio
async def test_unnotified_user_ids_skips_dedupe_when_no_work_is_needed() -> None:
    candidates = [uuid4(), uuid4()]
    db = AsyncMock()
    with patch.object(
        news_events, "lock_notification_dedupe", new_callable=AsyncMock
    ) as lock:
        assert (
            await news_events._unnotified_user_ids(db, None, candidates) == candidates
        )
        assert (
            await news_events._unnotified_user_ids(db, "news.created:empty", []) == []
        )

    lock.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_notification_times_use_campus_timezone(monkeypatch) -> None:
    """AUD-199: event notifications show start times in the campus zone, not the host's."""
    from app.core.config import settings as app_settings

    # +14:00 is unlikely to match the host zone, so a host-local conversion fails.
    monkeypatch.setattr(app_settings, "campus_timezone", "Pacific/Kiritimati")
    event = _event(starts_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
    render = MagicMock(return_value=None)
    with (
        patch.object(news_events, "normalize_locale", return_value="en"),
        patch.object(news_events, "render_notification_template", render),
        patch.object(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(
            news_events,
            "_unnotified_user_ids",
            AsyncMock(side_effect=lambda _db, _key, candidate_ids: candidate_ids),
        ),
        patch.object(
            news_events, "create_notifications_for_users", AsyncMock(return_value=1)
        ),
    ):
        await news_events.notify_about_event(AsyncMock(), event, locale="en")

    template_payload = render.call_args.args[1]
    assert template_payload["date"] == "19.10"
    assert template_payload["time"] == "02:00"
