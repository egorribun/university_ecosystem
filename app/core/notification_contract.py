"""Canonical cross-channel notification contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

CANONICAL_NOTIFICATION_TOPICS: Final[tuple[str, ...]] = (
    "news.published",
    "schedule.changed",
    "events.published",
    "chat.message.created",
    "system.release",
)

LEGACY_NOTIFICATION_TOPIC_ALIASES: Final[Mapping[str, str]] = {
    "news": "news.published",
    "schedule": "schedule.changed",
    "events": "events.published",
    "chat": "chat.message.created",
    "system": "system.release",
}


def canonicalize_notification_topic(value: object) -> str:
    """Return a normalized topic, migrating the previous short identifiers."""

    normalized = str(value).strip().lower()
    return LEGACY_NOTIFICATION_TOPIC_ALIASES.get(normalized, normalized)


def infer_notification_topic(notification_type: object) -> str | None:
    """Map an existing notification type to its canonical delivery topic."""

    if not isinstance(notification_type, str):
        return None
    normalized = notification_type.strip().lower()
    exact_types = {
        "news": "news.published",
        "schedule": "schedule.changed",
        "event": "events.published",
        "events": "events.published",
        "chat": "chat.message.created",
        "system": "system.release",
    }
    if normalized in exact_types:
        return exact_types[normalized]
    prefixes = {
        "news.": "news.published",
        "schedule.": "schedule.changed",
        "event.": "events.published",
        "events.": "events.published",
        "chat.": "chat.message.created",
        "system.": "system.release",
    }
    return next(
        (topic for prefix, topic in prefixes.items() if normalized.startswith(prefix)),
        None,
    )


def build_notification_metadata(
    *,
    notification_id: object,
    topic: str | None,
    notification_type: str | None,
    url: str | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build immutable identity metadata shared by in-app, live and Web Push."""

    metadata = dict(extra or {})
    metadata.update(
        {
            "notificationId": str(notification_id),
            "topic": topic,
            "type": notification_type,
            "url": url or "/",
        }
    )
    return metadata
