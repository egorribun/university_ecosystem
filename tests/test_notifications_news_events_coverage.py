"""Coverage tests for app/services/notifications/news_events.py (testing session 9).

Targets ``notify_about_comment`` (previously fully uncovered, L383-413).
``_fetch_admin_ids`` is imported INSIDE the function from
app.services.notifications.core, so it is monkeypatched on the core module;
``create_notifications_for_users`` and ``render_notification_template`` are
module-level imports on news_events and are patched there.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.notifications import core as notifications_core
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
    return SimpleNamespace(content=content)


def _make_author(**overrides):
    defaults = {"full_name": "Иван Петров", "username": "ivan"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def fake_create(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=3)
    monkeypatch.setattr(news_events, "create_notifications_for_users", mock)
    return mock


@pytest.fixture
def admin_ids(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(
        notifications_core, "_fetch_admin_ids", AsyncMock(return_value=ids)
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
    assert kwargs["topic"] == "news"
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
