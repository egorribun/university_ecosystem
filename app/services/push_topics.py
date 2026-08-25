"""Helpers for working with push notification topics."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import attributes as orm_attributes

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.notification_contract import (
    CANONICAL_NOTIFICATION_TOPICS as CANONICAL_NOTIFICATION_TOPICS,
)
from app.core.notification_contract import (
    canonicalize_notification_topic,
)
from app.models import PushSubscription, UserPushTopic

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    from app.core.protocols import AsyncDatabaseSession as AsyncSession


def get_allowed_topics(settings_obj: Settings | None = None) -> list[str]:
    """Return allowed push topics using the provided settings."""

    current_settings = settings_obj or app_settings
    return list(current_settings.notifications_allowed_push_topics_list)


def sort_topics(
    topics: Iterable[str] | None,
    *,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> list[str]:
    """Normalize topics and return them ordered according to the allowed list."""

    normalized = normalize_topics(
        topics,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    allowed_list = (
        list(allowed_topics)
        if allowed_topics is not None
        else get_allowed_topics(settings_obj)
    )
    order = {topic: index for index, topic in enumerate(allowed_list)}
    return sorted(normalized, key=lambda topic: order.get(topic, len(order)))


def _resolve_allowed_topics(
    allowed_topics: Collection[str] | None,
    settings_obj: Settings | None,
) -> frozenset[str]:
    if allowed_topics is not None:
        return frozenset(topic.strip().lower() for topic in allowed_topics if topic)
    current_settings = settings_obj or app_settings
    return current_settings.notifications_allowed_push_topics_set


def normalize_topic(
    value: str | None,
    *,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
    strict: bool = False,
) -> str | None:
    """Normalize a single topic value.

    Returns the normalized topic (lowercase) if it is allowed. Unknown topics
    are ignored unless ``strict`` is ``True``.
    """

    if value is None:
        return None
    raw_normalized = str(value).strip().lower()
    if not raw_normalized:
        return None
    allowed = _resolve_allowed_topics(allowed_topics, settings_obj)
    normalized = (
        raw_normalized
        if raw_normalized in allowed
        else canonicalize_notification_topic(raw_normalized)
    )
    if normalized not in allowed:
        if strict:
            raise ValueError(f"Unknown notification topic: {value!r}")
        return None
    return normalized


def normalize_topics(
    raw_topics: Iterable[str] | None,
    *,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
    strict: bool = False,
) -> list[str]:
    """Normalize and deduplicate an iterable of topics."""

    result: list[str] = []
    seen: set[str] = set()
    if raw_topics is None:
        return result
    for raw in raw_topics:
        normalized = normalize_topic(
            raw,
            allowed_topics=allowed_topics,
            settings_obj=settings_obj,
            strict=strict,
        )
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def resolve_topics(
    raw_topics: Iterable[str] | None,
    existing: Sequence[str] | None = None,
    *,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> list[str]:
    """Resolve topics from a raw payload, falling back to existing values."""

    if raw_topics is None:
        return normalize_topics(
            existing or [],
            allowed_topics=allowed_topics,
            settings_obj=settings_obj,
        )
    return normalize_topics(
        raw_topics,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )


def subscription_supports_topic(
    subscription: PushSubscription | None,
    topic: str | None,
    *,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> bool:
    """Check whether a subscription is interested in the provided topic."""

    normalized_topic = normalize_topic(
        topic,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    if normalized_topic is None:
        return True
    if subscription is None:
        return False

    user = getattr(subscription, "user", None)
    preferences = None
    if user is not None:
        try:
            state = orm_attributes.instance_state(user)
            if "push_topic_preferences" not in state.unloaded:
                preferences = getattr(user, "push_topic_preferences", None)
        except (AttributeError, TypeError):
            # RZ-20-04: Narrowed — SQLAlchemy state inspection edge cases.
            preferences = getattr(user, "push_topic_preferences", None)
    allowed_by_user = True
    if preferences is not None:
        user_topics = normalize_topics(
            getattr(preferences, "topics", None),
            allowed_topics=allowed_topics,
            settings_obj=settings_obj,
        )
        allowed_by_user = normalized_topic in user_topics

    stored = getattr(subscription, "topics", None)
    normalized_existing = normalize_topics(
        stored,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    if normalized_existing:
        return allowed_by_user and (normalized_topic in normalized_existing)
    return allowed_by_user


async def upsert_user_topics(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    topics: Iterable[str] | None,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> list[str]:
    """Persist normalized user topic preferences without committing."""

    normalized = normalize_topics(
        topics,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    existing = (
        await db.execute(select(UserPushTopic).where(UserPushTopic.user_id == user_id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(UserPushTopic(user_id=user_id, topics=list(normalized)))
    else:
        existing.topics = list(normalized)
    return list(normalized)


async def synchronize_user_topics(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    topics: Iterable[str] | None,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> list[str]:
    """Update user preferences and mirror them to all subscriptions."""

    normalized = await upsert_user_topics(
        db,
        user_id=user_id,
        topics=topics,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    subscriptions = (
        (
            await db.execute(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    normalized_copy = list(normalized)
    for subscription in subscriptions:
        subscription.topics = list(normalized_copy)
    return normalized_copy


async def filter_user_ids_by_topic(
    db: AsyncSession,
    *,
    user_ids: Sequence[uuid.UUID],
    topic: str | None,
    allowed_topics: Collection[str] | None = None,
    settings_obj: Settings | None = None,
) -> list[uuid.UUID]:
    """Apply the canonical topic preference to every delivery channel.

    Users without an explicit preference record retain the backwards-compatible
    opt-in default. An explicit empty topic list opts out of all topics.
    """

    normalized_topic = normalize_topic(
        topic,
        allowed_topics=allowed_topics,
        settings_obj=settings_obj,
    )
    ordered_ids = list(dict.fromkeys(user_ids))
    if normalized_topic is None or not ordered_ids:
        return ordered_ids
    rows = (
        await db.execute(
            select(UserPushTopic.user_id, UserPushTopic.topics).where(
                UserPushTopic.user_id.in_(ordered_ids)
            )
        )
    ).all()
    preferences = {
        uuid.UUID(str(user_id)): normalize_topics(
            topics,
            allowed_topics=allowed_topics,
            settings_obj=settings_obj,
        )
        for user_id, topics in rows
    }
    return [
        user_id
        for user_id in ordered_ids
        if user_id not in preferences or normalized_topic in preferences[user_id]
    ]
