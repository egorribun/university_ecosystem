"""AUD-272: the Web Push claim ledger admits one send per notification and subscription."""

from __future__ import annotations

import typing
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Notification, NotificationDeliveryOnce, PushSubscription
from app.services import webpush as webpush_module
from app.services.notifications import delivery as notifications_delivery
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
def no_process_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(_results: object) -> None:
        return None

    monkeypatch.setattr(webpush_module, "process_push_results", _noop)


async def _add_subscription(db: AsyncSession, user_id: uuid.UUID) -> PushSubscription:
    subscription = PushSubscription(
        user_id=user_id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh="p256dh-key",  # pragma: allowlist secret
        auth="auth-key",  # pragma: allowlist secret
        created_at=datetime.now(UTC),
        topics=[],
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def _add_notification(db: AsyncSession, user_id: uuid.UUID) -> Notification:
    notification = Notification(
        user_id=user_id,
        title="Published",
        title_en="Published EN",
        body="Body",
        body_en="Body EN",
        type="news",
        url="/news/42",
        created_at=datetime.now(UTC),
        read=False,
    )
    db.add(notification)
    await db.flush()
    return notification


async def _claim_count(db: AsyncSession) -> int:
    return int(
        (
            await db.execute(select(func.count()).select_from(NotificationDeliveryOnce))
        ).scalar_one()
    )


def _stub_sender(
    monkeypatch: pytest.MonkeyPatch, statuses: list[str]
) -> list[uuid.UUID]:
    """Record each send attempt and answer with the next scripted status."""

    attempts: list[uuid.UUID] = []

    async def _send(sub: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        attempts.append(uuid.UUID(str(sub.id)))
        status = statuses.pop(0) if statuses else "sent"
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status=status,  # type: ignore[arg-type]
            status_code=201 if status == "sent" else 503,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _send)
    return attempts


@pytest.mark.asyncio
async def test_pair_already_claimed_by_another_attempt_is_not_sent(
    db_session,
    user_factory,
    push_configured,
    no_process_results,
    monkeypatch,
):
    user = await user_factory()
    subscription = await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    await db_session.execute(
        insert(NotificationDeliveryOnce).values(
            id=uuid.uuid4(),
            notification_id=notification.id,
            subscription_id=subscription.id,
            channel="webpush",
        )
    )
    await db_session.commit()
    attempts = _stub_sender(monkeypatch, [])

    outcome = await notifications_delivery.redeliver_notifications(
        db_session, notification_ids=[notification.id]
    )

    assert attempts == []
    assert outcome.sent == 0
    assert outcome.already_delivered == 1


@pytest.mark.asyncio
async def test_successful_send_keeps_its_claim(
    db_session,
    user_factory,
    push_configured,
    no_process_results,
    monkeypatch,
):
    user = await user_factory()
    subscription = await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    await db_session.commit()
    attempts = _stub_sender(monkeypatch, ["sent"])

    outcome = await notifications_delivery.redeliver_notifications(
        db_session, notification_ids=[notification.id]
    )

    assert outcome.sent == 1
    assert attempts == [uuid.UUID(str(subscription.id))]
    assert await _claim_count(db_session) == 1


@pytest.mark.asyncio
async def test_failed_send_releases_its_claim_so_the_retry_sends(
    db_session,
    user_factory,
    push_configured,
    no_process_results,
    monkeypatch,
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    await db_session.commit()
    attempts = _stub_sender(monkeypatch, ["error", "sent"])

    first = await notifications_delivery.redeliver_notifications(
        db_session, notification_ids=[notification.id]
    )
    assert first.retryable_failures == 1
    assert await _claim_count(db_session) == 0

    second = await notifications_delivery.redeliver_notifications(
        db_session, notification_ids=[notification.id]
    )

    assert second.sent == 1
    assert len(attempts) == 2
    assert await _claim_count(db_session) == 1


@pytest.mark.asyncio
async def test_claim_helpers_without_pairs_issue_no_sql():
    db = MagicMock()
    db.execute = AsyncMock()

    claimed = await notifications_delivery._claim_web_push_deliveries(db, [])
    await notifications_delivery._release_web_push_claims(db, [])

    assert claimed == set()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_on_postgresql_uses_conflict_skip_and_returns_only_new_claims():
    notification_id = uuid.uuid4()
    subscription_id = uuid.uuid4()
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    claimed_rows = MagicMock()
    claimed_rows.all.return_value = [(notification_id, subscription_id)]
    db.execute = AsyncMock(return_value=claimed_rows)

    claimed = await notifications_delivery._claim_web_push_deliveries(
        db, [(notification_id, subscription_id)]
    )

    assert claimed == {(notification_id, subscription_id)}
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT DO NOTHING" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_claim_helper_fails_closed_on_unsupported_dialect():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "mysql"

    with pytest.raises(RuntimeError, match="PostgreSQL or SQLite"):
        await notifications_delivery._claim_web_push_deliveries(
            db, [(uuid.uuid4(), uuid.uuid4())]
        )
