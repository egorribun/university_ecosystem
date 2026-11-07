"""AUD-272: the Web Push claim ledger admits one send per notification and subscription."""

from __future__ import annotations

import typing
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Table, UniqueConstraint, func, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryOnce,
    PushSubscription,
)
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
        p256dh=uuid.uuid4().hex,
        auth=uuid.uuid4().hex,
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
    monkeypatch: pytest.MonkeyPatch,
    statuses: list[typing.Literal["sent", "gone", "error"]],
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
            status=status,
            status_code=201 if status == "sent" else 503,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _send)
    return attempts


def test_attempt_keyed_unique_constraint_is_gone_and_the_claim_ledger_keys_the_pair() -> (
    None
):
    """AUD-272: delivery-once is the ledger's (notification, subscription, channel) key.

    notification_deliveries keeps only its non-unique dedup index; the constraint that
    also keyed on attempted_at no longer exists in the ORM metadata.
    """
    delivery_table = typing.cast(Table, NotificationDelivery.__table__)
    delivery_constraints = {
        constraint.name for constraint in delivery_table.constraints
    }
    assert "uq_notification_delivery_once" not in delivery_constraints

    ledger = typing.cast(Table, NotificationDeliveryOnce.__table__)
    unique_ledger = [
        constraint
        for constraint in ledger.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_notification_delivery_once_claim"
    ]
    assert len(unique_ledger) == 1
    assert [column.name for column in unique_ledger[0].columns] == [
        "notification_id",
        "subscription_id",
        "channel",
    ]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "error"])
async def test_postprocessing_failure_cannot_roll_back_delivery_progress(
    db_session,
    user_factory,
    push_configured,
    monkeypatch,
    status,
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    notification_id = notification.id
    await db_session.commit()
    attempts = _stub_sender(monkeypatch, [status, "sent"])
    processor = AsyncMock(side_effect=RuntimeError("post-processing unavailable"))
    monkeypatch.setattr(webpush_module, "process_push_results", processor)

    with pytest.raises(RuntimeError, match="post-processing unavailable"):
        await notifications_delivery.redeliver_notifications(
            db_session, notification_ids=[notification_id]
        )
    # Match the caller's failure cleanup: it must not erase a successful claim.
    await db_session.rollback()
    assert await _claim_count(db_session) == (1 if status == "sent" else 0)
    processor.assert_awaited_once()
    monkeypatch.setattr(webpush_module, "process_push_results", AsyncMock())

    replay = await notifications_delivery.redeliver_notifications(
        db_session, notification_ids=[notification_id]
    )

    assert len(attempts) == (1 if status == "sent" else 2)
    assert replay.already_delivered == (1 if status == "sent" else 0)
    assert replay.sent == (0 if status == "sent" else 1)
    assert await _claim_count(db_session) == 1


@pytest.mark.asyncio
async def test_retention_keeps_replayable_claims_and_expires_only_old_orphans(
    db_session, user_factory, monkeypatch
):
    from datetime import timedelta

    from app.services.notifications.cleanup import cleanup_stale_notifications

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    old = cutoff - timedelta(seconds=1)
    user = await user_factory()
    notification = await _add_notification(db_session, user.id)
    notification.created_at = old
    notification_id = notification.id
    orphan_old, orphan_boundary, orphan_fresh, retained = [
        uuid.uuid4() for _ in range(4)
    ]
    claims = [
        (orphan_old, uuid.uuid4(), old),
        (orphan_boundary, uuid.uuid4(), cutoff),
        (orphan_fresh, uuid.uuid4(), now),
        (retained, notification_id, old),
    ]
    await db_session.execute(
        insert(NotificationDeliveryOnce),
        [
            {
                "id": claim_id,
                "notification_id": notice_id,
                "subscription_id": uuid.uuid4(),
                "channel": "webpush",
                "created_at": created,
            }
            for claim_id, notice_id, created in claims
        ],
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "notifications_retention_batch_size", 1)

    result = await cleanup_stale_notifications(
        db=db_session, retention_days=30, now=now
    )
    remaining = set(
        (await db_session.scalars(select(NotificationDeliveryOnce.id))).all()
    )

    assert result == (0, 0)
    assert remaining == {orphan_boundary, orphan_fresh, retained}
    assert (
        await db_session.scalar(
            select(Notification.id).where(Notification.id == notification_id)
        )
        == notification_id
    )
    notification.read = True
    await db_session.commit()

    result = await cleanup_stale_notifications(
        db=db_session, retention_days=30, now=now
    )
    remaining = set(
        (await db_session.scalars(select(NotificationDeliveryOnce.id))).all()
    )

    assert result == (1, 0)
    assert remaining == {orphan_boundary, orphan_fresh}


@pytest.mark.asyncio
async def test_delivery_commit_failure_never_runs_subscription_postprocessing(
    db_session, user_factory, push_configured, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    notification_id = notification.id
    await db_session.commit()
    attempts = _stub_sender(monkeypatch, ["sent"])
    processor = AsyncMock()
    monkeypatch.setattr(webpush_module, "process_push_results", processor)
    monkeypatch.setattr(
        db_session, "commit", AsyncMock(side_effect=RuntimeError("commit unavailable"))
    )

    with pytest.raises(RuntimeError, match="commit unavailable"):
        await notifications_delivery.redeliver_notifications(
            db_session, notification_ids=[notification_id]
        )

    assert len(attempts) == 1
    processor.assert_not_awaited()
    await db_session.rollback()
    assert await _claim_count(db_session) == 0
