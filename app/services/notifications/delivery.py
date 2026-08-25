"""Notification delivery functionality.

This module handles the creation and delivery of notifications to users,
including push notification sending via web push.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
import uuid as _uuid_mod
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger
from app.core.notification_contract import (
    build_notification_metadata,
    infer_notification_topic,
)
from app.models import (
    Notification,
    NotificationDelivery,
    PushSubscription,
    User,
)
from app.services import stats_cache
from app.services import webpush as webpush_module
from app.services.notifications.core import (
    _build_delivery_row,
    _coerce_optional_text,
    _normalize_translation_map,
)
from app.services.notifications.quiet_hours import prepare_push_payload_for_user
from app.services.push_topics import (
    filter_user_ids_by_topic,
    normalize_topic,
    subscription_supports_topic,
)
from app.services.webpush import WebPushResult
from app.utils.uuid_v7 import generate_uuid7

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationRedeliveryOutcome:
    """Persisted result of one outbox-driven delivery attempt."""

    sent: int = 0
    already_delivered: int = 0
    terminal_failures: int = 0
    retryable_failures: int = 0


class NotificationRedeliveryError(RuntimeError):
    """Signal retryable Web Push failures to the transactional outbox worker."""

    def __init__(self, outcome: NotificationRedeliveryOutcome) -> None:
        self.outcome = outcome
        super().__init__(
            f"Web Push redelivery has {outcome.retryable_failures} retryable failure(s)"
        )


def _is_push_configured() -> bool:
    """Return True when VAPID credentials are available for push delivery."""
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)


# Re-export for backward compatibility (used in _send_push)
send_web_push = webpush_module.send_web_push


def only_active_users(stmt: Select[Any]) -> Select[Any]:
    """Limit a user selection to accounts that are currently active."""

    return stmt.where(User.is_active.is_(True))


def _unique_notification_ids(values: Sequence[uuid.UUID | str]) -> list[uuid.UUID]:
    """Return valid notification UUIDs once, retaining their event order."""

    identifiers: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for value in values:
        try:
            identifier = uuid.UUID(str(value))
        except (AttributeError, TypeError, ValueError):
            logger.warning("Ignoring invalid notification id in outbox event")
            continue
        if identifier not in seen:
            seen.add(identifier)
            identifiers.append(identifier)
    return identifiers


async def redeliver_notifications(
    db: AsyncSession,
    *,
    notification_ids: Sequence[uuid.UUID | str],
    channel: str = "push",
) -> NotificationRedeliveryOutcome:
    """Deliver stored notifications and persist an idempotency journal.

    Successful ``(notification, subscription)`` pairs are never sent again.
    Notification row locks serialize overlapping outbox events on PostgreSQL;
    retryable provider failures are recorded so the caller can commit partial
    progress before asking the outbox worker to retry the event.
    """

    if channel != "push":
        raise ValueError(f"Unsupported notification delivery channel: {channel!r}")
    identifiers = _unique_notification_ids(notification_ids)
    if not identifiers:
        return NotificationRedeliveryOutcome()
    if not _is_push_configured():
        raise NotificationRedeliveryError(
            NotificationRedeliveryOutcome(retryable_failures=len(identifiers))
        )

    notification_rows = await db.execute(
        select(Notification)
        .where(Notification.id.in_(identifiers))
        .order_by(Notification.id)
        .with_for_update()
    )
    notifications = list(notification_rows.scalars().all())
    if not notifications:
        return NotificationRedeliveryOutcome()

    user_ids = list({uuid.UUID(str(item.user_id)) for item in notifications})
    subscription_rows = await db.execute(
        select(PushSubscription)
        .options(
            selectinload(PushSubscription.user).selectinload(
                User.push_topic_preferences
            )
        )
        .where(PushSubscription.user_id.in_(user_ids))
    )
    subscriptions_by_user: defaultdict[uuid.UUID, list[PushSubscription]] = defaultdict(
        list
    )
    subscriptions: list[PushSubscription] = []
    for subscription in subscription_rows.scalars().all():
        user_id = uuid.UUID(str(subscription.user_id))
        subscriptions_by_user[user_id].append(subscription)
        subscriptions.append(subscription)

    subscription_ids = [uuid.UUID(str(item.id)) for item in subscriptions]
    delivered_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    prior_attempts: dict[tuple[uuid.UUID, uuid.UUID], NotificationDelivery] = {}
    if subscription_ids:
        delivered_rows = await db.execute(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.notification_id.in_(identifiers),
                NotificationDelivery.channel == "webpush",
                NotificationDelivery.subscription_id.in_(subscription_ids),
            )
            .order_by(NotificationDelivery.attempted_at.desc())
        )
        for delivery in delivered_rows.scalars().all():
            if delivery.subscription_id is None:
                continue
            pair = (
                uuid.UUID(str(delivery.notification_id)),
                uuid.UUID(str(delivery.subscription_id)),
            )
            prior_attempts.setdefault(pair, delivery)
            if delivery.status == "sent":
                delivered_pairs.add(pair)

    already_delivered = 0
    terminal_failures = 0
    send_jobs: list[tuple[Notification, PushSubscription]] = []
    tasks: list[Awaitable[WebPushResult]] = []
    for notification in notifications:
        notification_id = uuid.UUID(str(notification.id))
        topic = normalize_topic(infer_notification_topic(notification.type))
        for subscription in subscriptions_by_user.get(
            uuid.UUID(str(notification.user_id)), []
        ):
            subscription_id = uuid.UUID(str(subscription.id))
            if (notification_id, subscription_id) in delivered_pairs:
                already_delivered += 1
                continue
            if not subscription_supports_topic(subscription, topic):
                terminal_failures += 1
                continue
            payload: dict[str, Any] = {
                "title": notification.title,
                "body": notification.body or "",
                "url": notification.url or "/",
                "type": notification.type,
                "tag": str(notification_id),
                "data": build_notification_metadata(
                    notification_id=notification_id,
                    topic=topic,
                    notification_type=notification.type,
                    url=notification.url,
                ),
            }
            if topic:
                payload["topic"] = topic
            prepared = prepare_push_payload_for_user(
                payload, getattr(subscription, "user", None)
            )
            send_jobs.append((notification, subscription))
            tasks.append(webpush_module._send_push_async(subscription, prepared))

    sent = 0
    retryable_failures = 0
    delivery_rows: list[dict[str, Any]] = []
    push_results: list[WebPushResult] = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (notification, subscription), result in zip(
            send_jobs, results, strict=True
        ):
            attempted_at = dt.datetime.now(UTC)
            notification_id = uuid.UUID(str(notification.id))
            subscription_id = uuid.UUID(str(subscription.id))
            prior_attempt = prior_attempts.get((notification_id, subscription_id))
            if isinstance(result, WebPushResult):
                push_results.append(result)
                if prior_attempt is None:
                    delivery_rows.append(
                        _build_delivery_row(
                            notification_id,
                            notification.created_at,
                            status=result.status,
                            subscription_id=subscription_id,
                            attempted_at=attempted_at,
                            delivered=result.status == "sent",
                            status_code=result.status_code,
                            detail=result.error,
                        )
                    )
                else:
                    prior_attempt.status = result.status
                    prior_attempt.delivered_at = (
                        attempted_at if result.status == "sent" else None
                    )
                    prior_attempt.status_code = result.status_code
                    prior_attempt.detail = result.error
                if result.status == "sent":
                    sent += 1
                    metrics.record_notification_delivered(
                        notification_type=str(notification.type or "unknown")
                    )
                elif result.status == "gone":
                    terminal_failures += 1
                    metrics.record_notification_failed(
                        notification_type=str(notification.type or "unknown"),
                        reason="gone",
                    )
                else:
                    retryable_failures += 1
                    metrics.record_notification_failed(
                        notification_type=str(notification.type or "unknown"),
                        reason="error",
                    )
            else:
                retryable_failures += 1
                detail = f"exception:{result}"
                if prior_attempt is None:
                    delivery_rows.append(
                        _build_delivery_row(
                            notification_id,
                            notification.created_at,
                            status="error",
                            subscription_id=subscription_id,
                            attempted_at=attempted_at,
                            detail=detail,
                        )
                    )
                else:
                    prior_attempt.status = "error"
                    prior_attempt.delivered_at = None
                    prior_attempt.status_code = None
                    prior_attempt.detail = detail
                metrics.record_notification_failed(
                    notification_type=str(notification.type or "unknown"),
                    reason="exception",
                )

    if delivery_rows:
        await db.execute(insert(NotificationDelivery).values(delivery_rows))
    await db.flush()
    if push_results:
        await webpush_module.process_push_results(push_results)

    return NotificationRedeliveryOutcome(
        sent=sent,
        already_delivered=already_delivered,
        terminal_failures=terminal_failures,
        retryable_failures=retryable_failures,
    )


async def create_notifications_for_users(
    db: AsyncSession,
    *,
    title: str,
    body: str | None = None,
    title_translations: Mapping[str, Any] | None = None,
    body_translations: Mapping[str, Any] | None = None,
    type: str | None = None,
    url: str | None = None,
    badge: str | None = None,
    tag: str | None = None,
    dedupe_key: str | None = None,
    actions: Sequence[Mapping[str, Any]] | None = None,
    payload_data: Mapping[str, Any] | None = None,
    user_ids: Sequence[uuid.UUID],
    topic: str | None = None,
    user_filter: Callable[[Select[Any]], Select[Any]] | None = None,
) -> int:
    """Create notifications for multiple users and send push notifications."""
    # DEBT-06 (audit 2026-03-15): Fail-fast before any DB operations when push is
    # not configured.  Notification rows are still created for in-app display only;
    # the early-exit here prevents creating delivery rows with status "skipped".
    # NOTE: This guard is intentionally for "push" channel only — the function
    # always writes Notification rows for in-app display; the guard only skips the
    # push-delivery path that requires VAPID keys.
    _push_enabled = _is_push_configured()
    now = dt.datetime.now(UTC)
    uids = list({uuid.UUID(str(uid)) for uid in user_ids})
    normalized_topic = normalize_topic(topic)
    if not uids:
        return 0

    if user_filter is not None:
        filtered_stmt = select(User.id).where(User.id.in_(uids))
        filtered_stmt = user_filter(filtered_stmt)
        filtered_rows = await db.execute(filtered_stmt)
        allowed_ids = {
            user_id for user_id in filtered_rows.scalars().all() if user_id is not None
        }
        uids = [uid for uid in uids if uid in allowed_ids]
        if not uids:
            return 0
    uids = await filter_user_ids_by_topic(db, user_ids=uids, topic=normalized_topic)
    if not uids:
        return 0
    title_map = _normalize_translation_map(title_translations)
    body_map = _normalize_translation_map(body_translations)

    title_ru = title_map.get("ru") or str(title)
    body_ru = body_map.get("ru") or _coerce_optional_text(body)
    notification_title_en = title_map.get("en")
    notification_body_en = body_map.get("en")

    notifications_data = [
        {
            "id": generate_uuid7(),
            "user_id": uid,
            "title": title_ru,
            "title_en": notification_title_en,
            "body": body_ru,
            "body_en": notification_body_en,
            "type": type,
            "url": url,
            "dedupe_key": dedupe_key,
            "created_at": now,
            "read": False,
        }
        for uid in uids
    ]

    batch_size = 5000
    notification_ids_by_user: dict[uuid.UUID, uuid.UUID] = {}

    for i in range(0, len(notifications_data), batch_size):
        batch = notifications_data[i : i + batch_size]
        stmt = insert(Notification).values(batch)
        await db.execute(stmt)
        for row in batch:
            notification_ids_by_user[uuid.UUID(str(row["user_id"]))] = cast(
                uuid.UUID, row["id"]
            )

    await db.flush()

    # RED-02 (audit 2026-03-14): Record a NotificationsRequested outbox event
    # atomically with the Notification rows so the OutboxWorker can drive push
    # delivery with at-least-once semantics.  The direct push dispatch below is
    # kept as the primary path; the outbox acts as a durability record and
    # retry mechanism when the in-process delivery fails or the process crashes.
    if notification_ids_by_user:  # pragma: no branch - uids is non-empty here
        from app.core.events import NotificationsRequested
        from app.models.domain_events import StoredEvent

        _batch_id = str(_uuid_mod.uuid4())
        outbox_event = StoredEvent(
            event_type=NotificationsRequested.EVENT_TYPE,
            aggregate_type="NotificationBatch",
            aggregate_id=_batch_id,
            payload={
                "_schema_version": 1,
                "notification_ids": [str(v) for v in notification_ids_by_user.values()],
                "channel": "push",
            },
        )
        db.add(outbox_event)

    if notification_ids_by_user and type == "grade":
        await stats_cache.invalidate_user_stats_cache(
            user_ids=list(notification_ids_by_user.keys()),
            kinds=("grades",),
        )

    delivery_rows: list[dict[str, Any]] = []

    if not _push_enabled:
        # DEBT-06: VAPID check was evaluated at function entry; log here where
        # the push path would have started so the debug context is informative.
        logger.debug(
            "Push delivery skipped: VAPID credentials not configured "
            "(notifications created in DB for in-app display only)"
        )
        return len(notification_ids_by_user)

    # PERF-02 (audit 2026-03-15): Single batch IN() query scoped to the users
    # that actually received notification rows (notification_ids_by_user.keys()),
    # not the full uids list which may include users blocked by user_filter.
    # Results are grouped into a defaultdict so multiple push subscriptions per
    # user are handled correctly without per-user round-trips.
    inserted_user_ids = list(notification_ids_by_user.keys())
    subs_result = await db.execute(
        select(PushSubscription)
        .options(
            selectinload(PushSubscription.user).selectinload(
                User.push_topic_preferences
            )
        )
        .where(PushSubscription.user_id.in_(inserted_user_ids))
    )
    subs_by_user: defaultdict[uuid.UUID, list[PushSubscription]] = defaultdict(list)
    for _sub in subs_result.scalars():
        _sub_user_id = getattr(_sub, "user_id", None)
        if _sub_user_id is not None:
            subs_by_user[uuid.UUID(str(_sub_user_id))].append(_sub)
    subs = [sub for sub_list in subs_by_user.values() for sub in sub_list]

    if not subs:
        attempt_ts = dt.datetime.now(UTC)
        for nid in notification_ids_by_user.values():
            delivery_rows.append(
                _build_delivery_row(
                    nid,
                    now,
                    status="skipped_no_subscription",
                    attempted_at=attempt_ts,
                )
            )
    else:
        base_payload: dict[str, Any] = {
            "title": title,
            "body": body or "",
            "url": url or "/",
            "type": type or None,
        }
        if normalized_topic:
            base_payload["topic"] = normalized_topic
        if badge:
            base_payload["badge"] = badge
        if tag:
            base_payload["tag"] = tag
        if actions:
            normalized_actions: list[dict[str, Any]] = []
            for action in actions:
                normalized = {
                    key: value
                    for key, value in action.items()
                    if key in {"action", "title", "icon", "url"}
                }
                if not normalized.get("action") or not normalized.get("title"):
                    continue
                normalized_actions.append(normalized)
            if normalized_actions:
                base_payload["actions"] = normalized_actions

        send_jobs: list[tuple[Any, Any]] = []
        tasks: list[Awaitable[WebPushResult]] = []

        # MOD-01 Fix: Use a high-level semaphore to control fan-out concurrency.
        # While the underlying service has its own lock, managing 5000+
        # in-flight coroutines can cause memory spikes and event-loop lag.
        _fanout_semaphore = asyncio.Semaphore(50)

        async def _send_push(
            subscription: PushSubscription, payload: Mapping[str, Any]
        ) -> WebPushResult:
            async with _fanout_semaphore:
                # RED-07 (audit 2026-03-15): Delegate to webpush_module._send_push_async
                # which enforces a 30-slot semaphore + 15 s asyncio.timeout per call.
                _send_func = send_web_push
                if _send_func is webpush_module.send_web_push:
                    return await webpush_module._send_push_async(
                        subscription, dict(payload)
                    )

                # Monkeypatched path (tests): preserve the override.
                try:
                    async with asyncio.timeout(15.0):
                        return await asyncio.to_thread(
                            _send_func, subscription, dict(payload)
                        )
                except TimeoutError:
                    import uuid as _uuid_local

                    user_id = getattr(subscription, "user_id", None)
                    logger.warning(
                        "WebPush timeout (test path) for subscription %s",
                        subscription.id,
                    )
                    return WebPushResult(
                        subscription_id=subscription.id,
                        endpoint=str(subscription.endpoint),
                        user_id=_uuid_local.UUID(str(user_id)) if user_id else None,
                        status="error",
                        error="push delivery timed out",
                    )

        for sub in subs:
            # ``subs_by_user`` only contains subscriptions with a non-null
            # user_id, so this conversion is guaranteed by the grouping above.
            user_id_raw = sub.user_id
            user_id = uuid.UUID(str(user_id_raw))
            notification_id = notification_ids_by_user.get(user_id)
            if not notification_id:
                continue
            if not subscription_supports_topic(sub, normalized_topic):
                delivery_rows.append(
                    _build_delivery_row(
                        uuid.UUID(str(notification_id)),
                        now,
                        status="skipped_topic",
                        subscription_id=uuid.UUID(str(sub.id)),
                    )
                )
                continue
            payload_for_subscription = dict(base_payload)
            payload_for_subscription["tag"] = str(notification_id)
            payload_for_subscription["data"] = build_notification_metadata(
                notification_id=uuid.UUID(str(notification_id)),
                topic=normalized_topic,
                notification_type=type,
                url=url,
                extra=payload_data,
            )
            prepared_payload = prepare_push_payload_for_user(
                payload_for_subscription, getattr(sub, "user", None)
            )
            send_jobs.append((sub, notification_id))
            tasks.append(_send_push(sub, prepared_payload))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_results = [r for r in results if isinstance(r, WebPushResult)]
            await webpush_module.process_push_results(valid_results)

            for (sub, notification_id), result in zip(send_jobs, results, strict=False):
                attempt_ts = dt.datetime.now(UTC)
                if isinstance(result, WebPushResult):
                    delivery_rows.append(
                        _build_delivery_row(
                            uuid.UUID(str(notification_id)),
                            now,
                            status=result.status,
                            subscription_id=uuid.UUID(str(sub.id)),
                            attempted_at=attempt_ts,
                            delivered=result.status == "sent",
                            status_code=result.status_code,
                            detail=result.error or None,
                        )
                    )
                    if result.status == "sent":
                        metrics.record_notification_delivered(
                            notification_type=str(type or "unknown")
                        )
                    else:
                        metrics.record_notification_failed(
                            notification_type=str(type or "unknown"),
                            reason=str(result.status),
                        )
                else:
                    delivery_rows.append(
                        _build_delivery_row(
                            uuid.UUID(str(notification_id)),
                            now,
                            status="error",
                            subscription_id=uuid.UUID(str(sub.id)),
                            attempted_at=attempt_ts,
                            detail=f"exception:{result}",
                        )
                    )
                    metrics.record_notification_failed(
                        notification_type=str(type or "unknown"), reason="exception"
                    )

    if delivery_rows:
        await db.execute(insert(NotificationDelivery).values(delivery_rows))
        await db.flush()

    return len(notifications_data)
