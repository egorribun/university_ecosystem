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
from datetime import UTC
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger
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
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import WebPushResult
from app.utils.uuid_v7 import generate_uuid7

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


def _is_push_configured() -> bool:
    """Return True when VAPID credentials are available for push delivery."""
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)


# Re-export for backward compatibility (used in _send_push)
send_web_push = webpush_module.send_web_push


def only_active_users(stmt: Select[Any]) -> Select[Any]:
    """Limit a user selection to accounts that are currently active."""

    return stmt.where(User.is_active.is_(True))


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
        normalized_topic = normalize_topic(topic)
        if normalized_topic:
            base_payload["topic"] = normalized_topic
        if badge:
            base_payload["badge"] = badge
        if tag:
            base_payload["tag"] = tag
        if payload_data:
            base_payload["data"] = dict(payload_data)
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
                _send_func = globals().get(
                    "send_web_push", webpush_module.send_web_push
                )
                if _send_func is webpush_module.send_web_push:
                    return await webpush_module._send_push_async(
                        subscription, dict(payload)
                    )

                # Monkeypatched path (tests): preserve the override.
                try:
                    async with asyncio.timeout(15.0):
                        return await asyncio.to_thread(
                            _send_func, subscription, payload
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
            prepared_payload = prepare_push_payload_for_user(
                base_payload, getattr(sub, "user", None)
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
