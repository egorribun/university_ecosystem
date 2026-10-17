"""Behavior tests for news and event notification services.

Targets ``notify_about_comment`` (previously fully uncovered, L383-413).
``_fetch_admin_ids`` is imported INSIDE the function from
app.services.notifications.core, so it is monkeypatched on the core module;
``create_notifications_for_users`` and ``render_notification_template`` are
module-level imports on news_events and are patched there.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Notification, PushSubscription
from app.models.domain_events import StoredEvent
from app.services.notifications import core as notifications_core
from app.services.notifications import delivery as notifications_delivery
from app.services.notifications import news_events


def _make_news(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "title": "Новость",
        "title_en": "News title",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_comment(content: str = "Great article!"):
    return SimpleNamespace(id=uuid.uuid4(), content=content)


def _make_event(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "title": "Событие",
        "title_en": "Event",
        "description": "Описание события",
        "description_en": "Event description",
        "about": "Подробнее",
        "about_en": "More details",
        "location": "Корпус А",
        "location_en": "Building A",
        "event_type": "Лекция",
        "event_type_en": "Lecture",
        "speaker": "Иван Петров",
        "starts_at": datetime(2026, 7, 27, 12, 30, tzinfo=UTC),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_author(**overrides):
    defaults = {"full_name": "Иван Петров", "username": "ivan"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def fake_create(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=3)
    monkeypatch.setattr(news_events, "create_notifications_for_users", mock)

    async def _allow_unnotified(_db, _key, user_ids):
        return list(user_ids)

    monkeypatch.setattr(news_events, "_unnotified_user_ids", _allow_unnotified)
    return mock


@pytest.fixture
def admin_ids(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(
        notifications_core, "_fetch_admin_ids", AsyncMock(return_value=ids)
    )
    return ids


@pytest.fixture
def active_ids(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(
        news_events, "_fetch_active_user_ids", AsyncMock(return_value=ids)
    )
    return ids


@pytest.mark.asyncio
async def test_notify_about_comment_sends_to_admins(fake_create, admin_ids):
    news = _make_news()
    result = await news_events.notify_about_comment(
        AsyncMock(), news, _make_comment(), _make_author(), locale="ru"
    )

    assert result == 3
    fake_create.assert_awaited_once()
    kwargs = fake_create.await_args.kwargs
    assert kwargs["type"] == "news.comment"
    assert kwargs["topic"] == "news.published"
    assert kwargs["user_ids"] == admin_ids
    assert kwargs["title"]
    assert kwargs["body"]
    assert kwargs["url"]
    assert kwargs["tag"]


@pytest.mark.asyncio
async def test_notify_about_comment_no_admins_returns_zero(fake_create, monkeypatch):
    monkeypatch.setattr(
        notifications_core, "_fetch_admin_ids", AsyncMock(return_value=[])
    )
    result = await news_events.notify_about_comment(
        AsyncMock(), _make_news(), _make_comment(), _make_author()
    )
    assert result == 0
    fake_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_about_comment_no_template_returns_zero(
    fake_create, admin_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )
    result = await news_events.notify_about_comment(
        AsyncMock(), _make_news(), _make_comment(), _make_author()
    )
    assert result == 0
    fake_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_about_comment_localizes_title_en(
    fake_create, admin_ids, monkeypatch
):
    """English locale resolves the localized news title for the template payload."""
    captured: dict = {}

    def _capture_template(name, payload, *, locale=None):
        captured["name"] = name
        captured["payload"] = dict(payload)
        captured["locale"] = locale
        return {
            "title": "t",
            "body": "b",
            "url": "/news/1",
            "tag": "news-comment",
            "data": {"k": "v"},
        }

    monkeypatch.setattr(news_events, "render_notification_template", _capture_template)
    news = _make_news(title="Русский заголовок", title_en="English title")
    await news_events.notify_about_comment(
        AsyncMock(), news, _make_comment("c"), _make_author(), locale="en"
    )

    assert captured["name"] == "news.comment"
    assert captured["payload"]["news_title"] == "English title"
    assert captured["payload"]["news_id"] == news.id
    kwargs = fake_create.await_args.kwargs
    assert kwargs["payload_data"] == {"k": "v"}


@pytest.mark.asyncio
async def test_notify_about_comment_author_fallback_to_username(
    fake_create, admin_ids, monkeypatch
):
    """Author without full_name falls back to username in the template payload."""
    captured: dict = {}

    def _capture_template(name, payload, *, locale=None):
        captured["payload"] = dict(payload)
        return {"title": "t", "body": "b", "url": "/u", "tag": "tg"}

    monkeypatch.setattr(news_events, "render_notification_template", _capture_template)
    author = _make_author(full_name=None, username="fallback-user")
    await news_events.notify_about_comment(
        AsyncMock(), _make_news(), _make_comment(), author
    )
    assert captured["payload"]["user_name"] == "fallback-user"


@pytest.mark.asyncio
async def test_notify_about_comment_payload_defaults_missing_data(
    fake_create, admin_ids, monkeypatch
):
    """Template without a 'data' key sends an empty payload_data mapping."""
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {"title": "t", "body": "b", "url": "/u", "tag": "tg"},
    )
    await news_events.notify_about_comment(
        AsyncMock(), _make_news(), _make_comment(), _make_author()
    )
    kwargs = fake_create.await_args.kwargs
    assert kwargs["payload_data"] == {}
    assert kwargs["dedupe_key"].startswith("news.comment:")
    assert kwargs["push_via_outbox_only"] is True


@pytest.mark.asyncio
async def test_notify_about_news_uses_localized_fallback_and_active_users(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )
    news = _make_news(
        content="<p>Краткое содержание</p>",
        content_en="<p>English summary</p>",
    )

    result = await news_events.notify_about_news(AsyncMock(), news, locale="ru")

    assert result == 3
    kwargs = fake_create.await_args.kwargs
    assert kwargs["type"] == "news.new"
    assert kwargs["topic"] == "news.published"
    assert kwargs["user_ids"] == active_ids
    assert kwargs["url"] == f"/news/{news.id}"
    assert kwargs["body"] == "Краткое содержание"
    assert kwargs["payload_data"]["category"] == "news"
    assert kwargs["dedupe_key"] == f"news.created:{news.id}"
    assert kwargs["push_via_outbox_only"] is True


@pytest.mark.asyncio
async def test_notify_about_news_template_and_no_users_paths(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {
            "title": "",
            "body": "",
            "url": "",
            "tag": "",
            "data": {"custom": "value"},
        },
    )
    news = _make_news(id=None, title="", title_en=None, content="", content_en=None)
    result = await news_events.notify_about_news(AsyncMock(), news, locale="en")

    assert result == 3
    kwargs = fake_create.await_args.kwargs
    assert kwargs["url"] == "/news"
    assert kwargs["tag"] == "news"
    assert kwargs["payload_data"]["custom"] == "value"
    assert kwargs["payload_data"]["category"] == "news"

    monkeypatch.setattr(
        news_events, "_fetch_active_user_ids", AsyncMock(return_value=[])
    )
    assert await news_events.notify_about_news(AsyncMock(), news) == 0


@pytest.mark.asyncio
async def test_notify_about_news_ignores_non_mapping_template_data(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {"data": ["not-a-mapping"]},
    )

    await news_events.notify_about_news(AsyncMock(), _make_news(), locale="ru")

    assert fake_create.await_args.kwargs["payload_data"]["category"] == "news"


@pytest.mark.asyncio
async def test_notify_about_event_uses_default_payload_and_active_users(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )
    event = _make_event()

    result = await news_events.notify_about_event(AsyncMock(), event, locale="ru")

    assert result == 3
    kwargs = fake_create.await_args.kwargs
    assert kwargs["type"] == "events.new"
    assert kwargs["topic"] == "events.published"
    assert kwargs["user_ids"] == active_ids
    assert kwargs["body"].startswith("Описание события\n")
    assert kwargs["payload_data"]["location"] == "Корпус А"
    assert kwargs["payload_data"]["speaker"] == "Иван Петров"
    assert kwargs["payload_data"]["eventType"] == "Лекция"
    assert kwargs["dedupe_key"] == f"events.created:{event.id}"
    assert kwargs["push_via_outbox_only"] is True


@pytest.mark.asyncio
async def test_notify_about_event_template_and_missing_optional_fields(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {
            "title": "Template title",
            "body": "Template body",
            "url": "/custom-event",
            "tag": "custom-event",
            "data": {"custom": "value"},
        },
    )
    event = _make_event(
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
        starts_at=datetime.now(UTC) - timedelta(hours=1),
    )

    result = await news_events.notify_about_event(AsyncMock(), event, locale="en")

    assert result == 3
    kwargs = fake_create.await_args.kwargs
    assert kwargs["title"] == "Template title"
    assert kwargs["url"] == "/custom-event"
    assert kwargs["tag"] == "custom-event"
    assert kwargs["payload_data"]["custom"] == "value"

    monkeypatch.setattr(
        news_events, "_fetch_active_user_ids", AsyncMock(return_value=[])
    )
    assert await news_events.notify_about_event(AsyncMock(), event) == 0


@pytest.mark.asyncio
async def test_notify_about_event_ignores_non_mapping_template_data(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {"data": ["not-a-mapping"]},
    )

    await news_events.notify_about_event(AsyncMock(), _make_event(), locale="ru")

    assert fake_create.await_args.kwargs["payload_data"]["category"] == "events"


@pytest.mark.asyncio
async def test_news_and_event_translation_loops_handle_empty_localized_values(
    fake_create, active_ids, monkeypatch
):
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )
    monkeypatch.setattr(news_events, "translate", lambda *a, **k: "")

    empty_news = _make_news(
        id=None,
        title="",
        title_en=None,
        content="",
        content_en=None,
    )
    await news_events.notify_about_news(AsyncMock(), empty_news, locale="ru")

    empty_event = _make_event(
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
    )
    await news_events.notify_about_event(AsyncMock(), empty_event, locale="ru")

    assert fake_create.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("topic", "entity_kind", "entity_id_key", "template_fallback"),
    [
        ("news.published", "news", "newsId", False),
        ("events.published", "event", "eventId", False),
        ("news.published", "news", "newsId", True),
        ("events.published", "event", "eventId", True),
    ],
)
async def test_news_and_event_push_metadata_is_json_serializable(
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
    topic: str,
    entity_kind: str,
    entity_id_key: str,
    template_fallback: bool,
) -> None:
    """Producer metadata must survive the durable push-outbox JSON boundary."""
    user = await user_factory()
    entity = _make_news() if entity_kind == "news" else _make_event()
    subscription = PushSubscription(
        user_id=user.id,
        endpoint="https://8.8.8.8/push-test",
        p256dh="test-p256dh",
        auth="test-auth",
        created_at=datetime.now(UTC),
        topics=[topic],
    )
    db_session.add(subscription)
    await db_session.flush()

    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: True)
    if template_fallback:
        # Exercise the producer's no-template path as well as the registered template.
        monkeypatch.setattr(
            news_events, "render_notification_template", lambda *a, **k: None
        )

    if entity_kind == "news":
        created = await news_events.notify_about_news(db_session, entity)
    else:
        created = await news_events.notify_about_event(db_session, entity)

    assert created == 1
    await db_session.flush()
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user.id)
    )
    assert notification is not None
    delivery_events = list(
        (
            await db_session.scalars(
                select(StoredEvent).where(
                    StoredEvent.event_type == "notification.delivery_requested"
                )
            )
        ).all()
    )
    delivery_event = next(
        event
        for event in delivery_events
        if str(notification.id) in event.payload["notification_ids"]
    )
    serialized_payload = json.loads(json.dumps(delivery_event.payload["payload_data"]))
    assert serialized_payload[entity_id_key] == str(entity.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["news", "event", "comment"])
async def test_notification_dedupe_skips_recipients_already_notified(
    fake_create, monkeypatch, kind
):
    db = AsyncMock()
    recipients = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(
        news_events,
        "_unnotified_user_ids",
        AsyncMock(return_value=[]),
    )

    if kind == "news":
        entity = _make_news()
        key = f"news.created:{entity.id}"
        monkeypatch.setattr(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=recipients)
        )
        result = await news_events.notify_about_news(db, entity, locale="en")
    elif kind == "event":
        entity = _make_event()
        key = f"events.created:{entity.id}"
        monkeypatch.setattr(
            news_events, "_fetch_active_user_ids", AsyncMock(return_value=recipients)
        )
        result = await news_events.notify_about_event(db, entity, locale="en")
    else:
        entity = _make_news()
        comment = _make_comment()
        key = f"news.comment:{comment.id}"
        monkeypatch.setattr(
            notifications_core, "_fetch_admin_ids", AsyncMock(return_value=recipients)
        )
        monkeypatch.setattr(
            news_events,
            "render_notification_template",
            lambda *args, **kwargs: {
                "title": "Comment",
                "body": "A new comment",
                "url": f"/news/{entity.id}",
                "tag": "news-comment",
            },
        )
        result = await news_events.notify_about_comment(
            db, entity, comment, _make_author(), locale="en"
        )

    assert result == 0
    news_events._unnotified_user_ids.assert_awaited_once_with(db, key, recipients)
    fake_create.assert_not_awaited()
