"""Focused unit coverage for delivery invariants not needing a database."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import User
from app.services import webpush as webpush_module
from app.services.notifications import delivery
from app.services.webpush import WebPushResult


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


def test_only_active_users_adds_active_predicate():
    statement = delivery.only_active_users(select(User.id))

    assert "users.is_active" in str(statement)


@pytest.mark.asyncio
async def test_allowed_user_filter_continues_to_notification_creation():
    user_id = uuid4()
    filter_result = MagicMock()
    filter_result.scalars.return_value.all.return_value = [user_id]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[filter_result, MagicMock()])
    db.flush = AsyncMock()
    db.add = MagicMock()

    def allow_all(statement):
        return statement

    with patch.object(delivery, "_is_push_configured", return_value=False):
        result = await delivery.create_notifications_for_users(
            db,
            title="Allowed",
            user_ids=[user_id],
            user_filter=allow_all,
        )

    assert result == 1
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_delivery_skips_subscription_without_user_id():
    user_id = uuid4()
    sub = SimpleNamespace(id=uuid4(), user_id=None)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), _ScalarResult([sub]), MagicMock()])
    db.flush = AsyncMock()
    db.add = MagicMock()

    with (
        patch.object(delivery, "_is_push_configured", return_value=True),
        patch.object(delivery, "subscription_supports_topic", return_value=True),
    ):
        result = await delivery.create_notifications_for_users(
            db,
            title="Invalid subscription",
            user_ids=[user_id],
            actions=[{"action": "", "title": ""}],
        )

    assert result == 1
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_delivery_skips_subscription_without_matching_notification():
    user_id = uuid4()
    sub = SimpleNamespace(id=uuid4(), user_id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), _ScalarResult([sub])])
    db.flush = AsyncMock()
    db.add = MagicMock()

    with patch.object(delivery, "_is_push_configured", return_value=True):
        result = await delivery.create_notifications_for_users(
            db,
            title="Unmatched subscription",
            user_ids=[user_id],
            actions=[{"action": "", "title": ""}],
        )

    assert result == 1
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_delivery_uses_async_webpush_path_for_unpatched_sender():
    user_id = uuid4()
    subscription_id = uuid4()
    sub = SimpleNamespace(
        id=subscription_id,
        user_id=user_id,
        endpoint="https://push.example.test/endpoint",
        user=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), _ScalarResult([sub]), MagicMock()])
    db.flush = AsyncMock()
    db.add = MagicMock()
    sent = WebPushResult(
        subscription_id=subscription_id,
        endpoint=sub.endpoint,
        user_id=user_id,
        status="sent",
    )

    with (
        patch.object(delivery, "_is_push_configured", return_value=True),
        patch.object(delivery, "subscription_supports_topic", return_value=True),
        patch.object(delivery, "prepare_push_payload_for_user", return_value={}),
        patch.object(
            webpush_module,
            "_send_push_async",
            new=AsyncMock(return_value=sent),
        ) as send,
        patch.object(webpush_module, "process_push_results", new=AsyncMock()),
    ):
        result = await delivery.create_notifications_for_users(
            db,
            title="Async path",
            user_ids=[user_id],
        )

    assert result == 1
    send.assert_awaited_once()
