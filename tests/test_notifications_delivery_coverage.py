"""Coverage tests for app/services/notifications/delivery.py (testing session 9).

Targets the previously-uncovered branches of ``create_notifications_for_users``:
user_filter exclusion, push-disabled early return, skipped_no_subscription,
payload badge/tag/actions normalization, skipped_topic, sent/error/exception
delivery rows and the grade-cache invalidation hook.

Harness mirrors tests/test_notifications_service.py (``configured_push_settings``
vapid fixture + ``send_web_push`` monkeypatch via the module-level override the
production code explicitly supports at delivery.py L264-277).
"""

from __future__ import annotations

import typing
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Notification, NotificationDelivery, PushSubscription
from app.services import stats_cache
from app.services import webpush as webpush_module
from app.services.notifications import delivery as notifications_delivery
from app.services.notifications.delivery import create_notifications_for_users
from app.services.webpush import WebPushResult


def _reset_vapid_cache() -> None:
    for cached in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "WEBPUSH_SUBJECT"):
        settings.__dict__.pop(cached, None)


@pytest.fixture
def push_configured(monkeypatch: pytest.MonkeyPatch) -> typing.Generator[None]:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com")
    yield
    _reset_vapid_cache()


@pytest.fixture
def push_disabled(monkeypatch: pytest.MonkeyPatch) -> typing.Generator[None]:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    yield
    _reset_vapid_cache()


async def _add_subscription(db: AsyncSession, user_id: uuid.UUID) -> PushSubscription:
    sub = PushSubscription(
        user_id=user_id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh="p256dh-key",  # pragma: allowlist secret
        auth="auth-key",  # pragma: allowlist secret
        created_at=datetime.now(UTC),
        topics=[],
    )
    db.add(sub)
    await db.flush()
    return sub


async def _delivery_rows_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[NotificationDelivery]:
    notif_ids = (
        (
            await db.execute(
                select(Notification.id).where(Notification.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if not notif_ids:
        return []
    rows = await db.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_(notif_ids)
        )
    )
    return list(rows.scalars().all())


@pytest.fixture
def no_process_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(_results):
        return None

    monkeypatch.setattr(webpush_module, "process_push_results", _noop)


# ---------------------------------------------------------------------------
# Early returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_user_ids_returns_zero(db_session):
    created = await create_notifications_for_users(db_session, title="T", user_ids=[])
    assert created == 0


@pytest.mark.asyncio
async def test_user_filter_excluding_all_returns_zero(db_session, user_factory):
    user = await user_factory()

    def _exclude_all(stmt):
        return stmt.where(False)

    created = await create_notifications_for_users(
        db_session,
        title="Filtered",
        user_ids=[user.id],
        user_filter=_exclude_all,
    )
    assert created == 0
    notifs = await _delivery_rows_for_user(db_session, user.id)
    assert notifs == []


@pytest.mark.asyncio
async def test_push_disabled_creates_notifications_without_deliveries(
    db_session, user_factory, push_disabled
):
    user = await user_factory()
    created = await create_notifications_for_users(
        db_session, title="In-app only", user_ids=[user.id]
    )
    assert created == 1
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
    ).scalar_one()
    assert notif.title == "In-app only"
    assert await _delivery_rows_for_user(db_session, user.id) == []


# ---------------------------------------------------------------------------
# Push-enabled paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_subscription_records_skipped_row(
    db_session, user_factory, push_configured
):
    user = await user_factory()
    created = await create_notifications_for_users(
        db_session, title="No subs", user_ids=[user.id]
    )
    assert created == 1
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["skipped_no_subscription"]


@pytest.mark.asyncio
async def test_sent_path_normalizes_payload(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    sub = await _add_subscription(db_session, user.id)
    payloads: list[dict] = []

    def _fake_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        payloads.append(dict(payload))
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    created = await create_notifications_for_users(
        db_session,
        title="Rich",
        body="Body",
        url="/rich",
        badge="/badge.png",
        tag="rich-tag",
        payload_data={"extra": "value"},
        actions=[
            {"action": "open", "title": "Open", "icon": "/i.png", "junk": "drop"},
            {"action": "no-title"},  # filtered: missing title
        ],
        user_ids=[user.id],
        topic="system",
    )
    assert created == 1

    rows = await _delivery_rows_for_user(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].delivered_at is not None
    assert rows[0].subscription_id == sub.id

    assert len(payloads) == 1
    sent_payload = payloads[0]
    assert sent_payload["badge"] == "/badge.png"
    assert sent_payload["tag"] == "rich-tag"
    assert sent_payload["data"] == {"extra": "value"}
    assert sent_payload["actions"] == [
        {"action": "open", "title": "Open", "icon": "/i.png"}
    ]
    assert sent_payload["topic"] == "system"


@pytest.mark.asyncio
async def test_error_result_records_error_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _fake_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="error",
            status_code=500,
            error="boom",
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    await create_notifications_for_users(db_session, title="Err", user_ids=[user.id])
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["error"]
    assert rows[0].delivered_at is None
    assert rows[0].detail == "boom"


@pytest.mark.asyncio
async def test_send_exception_records_exception_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _raise_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        raise RuntimeError("push exploded")

    monkeypatch.setattr(notifications_delivery, "send_web_push", _raise_send)

    await create_notifications_for_users(db_session, title="Boom", user_ids=[user.id])
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["error"]
    assert rows[0].detail is not None
    assert rows[0].detail.startswith("exception:")


@pytest.mark.asyncio
async def test_unsupported_topic_records_skipped_topic_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    monkeypatch.setattr(
        notifications_delivery,
        "subscription_supports_topic",
        lambda _sub, _topic: False,
    )

    sent_calls: list = []

    def _fake_send(s, payload):
        sent_calls.append(payload)
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="sent",
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    await create_notifications_for_users(
        db_session, title="Topic", user_ids=[user.id], topic="news"
    )
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["skipped_topic"]
    assert sent_calls == []


@pytest.mark.asyncio
async def test_grade_type_invalidates_stats_cache(
    db_session, user_factory, push_disabled, monkeypatch
):
    user = await user_factory()
    invalidate = AsyncMock()
    monkeypatch.setattr(stats_cache, "invalidate_user_stats_cache", invalidate)

    await create_notifications_for_users(
        db_session, title="Grade!", type="grade", user_ids=[user.id]
    )
    invalidate.assert_awaited_once()
    kwargs = invalidate.await_args.kwargs
    assert kwargs["user_ids"] == [user.id]
    assert kwargs["kinds"] == ("grades",)


@pytest.mark.asyncio
async def test_translations_populate_localized_columns(
    db_session, user_factory, push_disabled
):
    user = await user_factory()
    await create_notifications_for_users(
        db_session,
        title="Fallback title",
        body="Fallback body",
        title_translations={"ru": "Заголовок", "en": "Title-EN", "xx": "skip"},
        body_translations={"ru": "Тело", "en": "Body-EN"},
        user_ids=[user.id],
    )
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
    ).scalar_one()
    assert notif.title == "Заголовок"
    assert notif.title_en == "Title-EN"
    assert notif.body == "Тело"
    assert notif.body_en == "Body-EN"
