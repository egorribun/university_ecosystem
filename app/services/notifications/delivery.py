"""Notification delivery functionality.

This module handles the creation and delivery of notifications to users,
including push notification sending via web push.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.core import metrics
from app.core.config import settings
from app.models.models import (
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
from app.services.push_schema import ensure_push_subscription_schema
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import WebPushResult

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (used in _send_push)
send_web_push = webpush_module.send_web_push


_SCHEMA_CHECK_LOCK = asyncio.Lock()
_SCHEMA_CHECK_MARKER: float | None = None


async def _ensure_push_subscription_schema_once(db: AsyncSession) -> None:
    """Ensure the push subscription schema exists once per process."""

    global _SCHEMA_CHECK_MARKER

    if _SCHEMA_CHECK_MARKER is not None:
        return

    async with _SCHEMA_CHECK_LOCK:
        if _SCHEMA_CHECK_MARKER is not None:
            return
        await ensure_push_subscription_schema(db)
        _SCHEMA_CHECK_MARKER = dt.datetime.now(UTC).timestamp()


def invalidate_push_subscription_schema_cache() -> None:
    """Reset the cached schema check state so it runs again on next use."""

    global _SCHEMA_CHECK_MARKER
    _SCHEMA_CHECK_MARKER = None


def only_active_users(stmt: Select) -> Select:
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
    user_ids: Sequence[int],
    topic: str | None = None,
    user_filter: Callable[[Select], Select] | None = None,
) -> int:
    """Create notifications for multiple users and send push notifications."""
    now = dt.datetime.now(UTC)
    uids = list({int(uid) for uid in user_ids})
    if not uids:
        return 0

    if user_filter is not None:
        filtered_stmt = select(User.id).where(User.id.in_(uids))
        filtered_stmt = user_filter(filtered_stmt)
        filtered_rows = await db.execute(filtered_stmt)
        allowed_ids = {
            int(user_id)
            for user_id in filtered_rows.scalars().all()
            if user_id is not None
        }
        uids = [uid for uid in uids if uid in allowed_ids]
        if not uids:
            return 0
    title_map = _normalize_translation_map(title_translations)
    body_map = _normalize_translation_map(body_translations)

    notifications: list[Notification] = []
    for uid in uids:
        title_ru = title_map.get("ru") or str(title)
        body_ru = body_map.get("ru") or _coerce_optional_text(body)
        notification_title_en = title_map.get("en")
        notification_body_en = body_map.get("en")
        notification = Notification(
            user_id=uid,
            title=title_ru,
            title_en=notification_title_en,
            body=body_ru,
            body_en=notification_body_en,
            type=type,
            url=url,
            dedupe_key=dedupe_key,
            created_at=now,
            read=False,
        )
        notifications.append(notification)
    db.add_all(notifications)
    await db.flush()
    notification_ids_by_user = {
        int(notification.user_id): int(notification.id)
        for notification in notifications
        if notification.id is not None
    }
    await db.commit()

    if notification_ids_by_user and type == "grade":
        await stats_cache.invalidate_user_stats_cache(
            user_ids=list(notification_ids_by_user.keys()),
            kinds=("grades",),
        )

    if not notification_ids_by_user:
        return 0

    vapid_ready = bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)
    delivery_rows: list[dict[str, Any]] = []

    if not vapid_ready:
        attempt_ts = dt.datetime.now(UTC)
        for notification_id in notification_ids_by_user.values():
            delivery_rows.append(
                _build_delivery_row(
                    notification_id,
                    now,
                    status="skipped_no_credentials",
                    attempted_at=attempt_ts,
                )
            )
    else:
        await _ensure_push_subscription_schema_once(db)
        subs = (
            (
                await db.execute(
                    select(PushSubscription)
                    .options(
                        selectinload(PushSubscription.user).selectinload(
                            User.push_topic_preferences
                        )
                    )
                    .where(PushSubscription.user_id.in_(uids))
                )
            )
            .scalars()
            .all()
        )

        if not subs:
            attempt_ts = dt.datetime.now(UTC)
            for notification_id in notification_ids_by_user.values():
                delivery_rows.append(
                    _build_delivery_row(
                        notification_id,
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
                    if not isinstance(action, Mapping):
                        continue
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

            send_jobs: list[tuple[PushSubscription, int]] = []
            tasks: list[Awaitable[WebPushResult]] = []

            limit = int(
                getattr(settings, "notifications_webpush_concurrency_limit", 0) or 0
            )
            semaphore: asyncio.Semaphore | None = None
            if limit > 0:
                semaphore = asyncio.Semaphore(limit)

            async def _send_push(
                subscription: PushSubscription, payload: Mapping[str, Any]
            ) -> WebPushResult:
                # Use globals() to allow monkeypatching send_web_push for tests
                _send_func = globals().get(
                    "send_web_push", webpush_module.send_web_push
                )
                if semaphore is None:
                    return await asyncio.to_thread(_send_func, subscription, payload)
                async with semaphore:
                    return await asyncio.to_thread(_send_func, subscription, payload)

            for sub in subs:
                user_id = int(getattr(sub, "user_id", 0) or 0)
                notification_id = notification_ids_by_user.get(user_id)
                if not notification_id:
                    continue
                if not subscription_supports_topic(sub, normalized_topic):
                    delivery_rows.append(
                        _build_delivery_row(
                            notification_id,
                            now,
                            status="skipped_topic",
                            detail=f"subscription:{sub.id}",
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

                for (sub, notification_id), result in zip(
                    send_jobs, results, strict=False
                ):
                    attempt_ts = dt.datetime.now(UTC)
                    if isinstance(result, WebPushResult):
                        detail_parts: list[str] = [f"subscription:{sub.id}"]
                        if result.error:
                            detail_parts.append(result.error)
                        delivery_rows.append(
                            _build_delivery_row(
                                notification_id,
                                now,
                                status=result.status,
                                attempted_at=attempt_ts,
                                delivered=result.status == "sent",
                                status_code=result.status_code,
                                detail="; ".join(detail_parts),
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
                                notification_id,
                                now,
                                status="error",
                                attempted_at=attempt_ts,
                                detail=f"subscription:{sub.id}; exception:{result}",
                            )
                        )
                        metrics.record_notification_failed(
                            notification_type=str(type or "unknown"), reason="exception"
                        )

    if delivery_rows:
        await db.execute(insert(NotificationDelivery).values(delivery_rows))
        await db.commit()

    return len(notifications)
