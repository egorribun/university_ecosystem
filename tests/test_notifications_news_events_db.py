"""Real ORM profile-path tests for comment notification display names."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.orm import joinedload, noload

from app.models.users import User
from app.services.notifications import core as notifications_core
from app.services.notifications import news_events


@pytest.mark.parametrize(
    ("full_name", "profile_missing", "profile_loaded", "expected_name"),
    [
        ("Visible Author", False, True, "Visible Author"),
        ("Visible Author", False, False, "Visible Author"),
        (None, False, False, "User"),
        ("", False, False, "User"),
        ("   ", False, False, "User"),
        (None, True, False, "User"),
        ("", False, True, "User"),
    ],
    ids=(
        "loaded-profile-name",
        "noload-profile-name",
        "null-profile-name",
        "empty-profile-name",
        "whitespace-profile-name",
        "missing-profile-row",
        "loaded-empty-profile-name",
    ),
)
@pytest.mark.asyncio
async def test_comment_notification_uses_real_profile_name_without_email(
    db_session,
    user_factory,
    monkeypatch,
    full_name,
    profile_missing,
    profile_loaded,
    expected_name,
):
    user = await user_factory(full_name=full_name)
    if profile_missing:
        assert user.profile is not None
        await db_session.delete(user.profile)
        await db_session.flush()

    profile_option = (
        joinedload(User.profile) if profile_loaded else noload(User.profile)
    )
    author = await db_session.get(
        User,
        user.id,
        options=(profile_option,),
        populate_existing=True,
    )
    assert author is not None
    if profile_loaded and not profile_missing:
        assert author.profile is not None
    else:
        assert author.profile is None

    captured: dict[str, object] = {}

    def _capture_template(_name, payload, *, locale=None):
        captured.update(payload)
        return {"title": "title", "body": "body", "url": "/news", "tag": "news"}

    monkeypatch.setattr(
        notifications_core,
        "_fetch_admin_ids",
        AsyncMock(return_value=[uuid.uuid4()]),
    )
    monkeypatch.setattr(
        news_events,
        "_unnotified_user_ids",
        AsyncMock(side_effect=lambda _db, _key, user_ids: list(user_ids)),
    )
    monkeypatch.setattr(news_events, "render_notification_template", _capture_template)
    monkeypatch.setattr(
        news_events, "create_notifications_for_users", AsyncMock(return_value=1)
    )

    profile_reads = 0

    def _count_profile_reads(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal profile_reads
        if "user_profiles" in statement.lower():
            profile_reads += 1

    engine = db_session.bind
    assert engine is not None
    event.listen(engine.sync_engine, "before_cursor_execute", _count_profile_reads)
    try:
        result = await news_events.notify_about_comment(
            db_session,
            SimpleNamespace(id=uuid.uuid4(), title="News", title_en=None),
            SimpleNamespace(id=uuid.uuid4(), content="Comment"),
            author,
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count_profile_reads)

    assert result == 1
    assert captured["user_name"] == expected_name
    assert user.email not in str(captured["user_name"])
    assert profile_reads <= 1
