"""Helpers for working with push notification topics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checking only
    from app.models.models import PushSubscription

ALLOWED_PUSH_TOPICS: set[str] = {"news", "schedule", "events", "system"}


def normalize_topic(value: str | None) -> str | None:
    """Normalize a single topic value.

    Returns the normalized topic (lowercase) if it is allowed, otherwise ``None``.
    """

    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in ALLOWED_PUSH_TOPICS:
        return None
    return normalized


def normalize_topics(raw_topics: Iterable[str] | None) -> list[str]:
    """Normalize and deduplicate an iterable of topics."""

    result: list[str] = []
    seen: set[str] = set()
    if raw_topics is None:
        return result
    for raw in raw_topics:
        normalized = normalize_topic(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def resolve_topics(
    raw_topics: Iterable[str] | None,
    existing: Sequence[str] | None = None,
) -> list[str]:
    """Resolve topics from a raw payload, falling back to existing values."""

    if raw_topics is None:
        return normalize_topics(existing or [])
    return normalize_topics(raw_topics)


def subscription_supports_topic(
    subscription: PushSubscription | None, topic: str | None
) -> bool:
    """Check whether a subscription is interested in the provided topic."""

    normalized_topic = normalize_topic(topic)
    if normalized_topic is None:
        return True
    if subscription is None:
        return False
    stored = getattr(subscription, "topics", None)
    normalized_existing = normalize_topics(stored)
    return normalized_topic in normalized_existing
