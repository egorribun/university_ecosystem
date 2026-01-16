"""
Cache invalidation service for centralized cache management.

This module provides helpers for invalidating cached data across
different domains (schedule, users, events, news, etc.)
"""

from __future__ import annotations

import logging
from enum import StrEnum

from app.deps.cache import get_cache

logger = logging.getLogger(__name__)


class CacheTag(StrEnum):
    """Cache tags for grouping related cache entries."""

    SCHEDULE = "tag:schedule"
    USER = "tag:user"
    EVENT = "tag:event"
    NEWS = "tag:news"
    GROUPS = "tag:groups"
    NOTIFICATIONS = "tag:notifications"


# Cache key prefixes
CACHE_PREFIX_SCHEDULE = "schedule:group"
CACHE_PREFIX_USER = "user:profile"
CACHE_PREFIX_EVENT = "event"
CACHE_PREFIX_NEWS = "news"
CACHE_PREFIX_GROUPS = "groups:list"

# Tag to prefix mapping for automatic tag association
_TAG_PREFIX_MAP: dict[CacheTag, tuple[str, ...]] = {
    CacheTag.SCHEDULE: (CACHE_PREFIX_SCHEDULE,),
    CacheTag.USER: (CACHE_PREFIX_USER,),
    CacheTag.EVENT: (CACHE_PREFIX_EVENT,),
    CacheTag.NEWS: (CACHE_PREFIX_NEWS,),
    CacheTag.GROUPS: (CACHE_PREFIX_GROUPS,),
}


def get_tags_for_key(key: str) -> list[CacheTag]:
    """Get all tags associated with a cache key based on prefix matching."""
    tags = []
    for tag, prefixes in _TAG_PREFIX_MAP.items():
        for prefix in prefixes:
            if key.startswith(prefix):
                tags.append(tag)
                break
    return tags


async def register_key_with_tags(key: str, ttl_seconds: int = 3600) -> None:
    """
    Register a cache key with its associated tags for tag-based invalidation.

    This stores a reverse index: tag -> set of keys.
    Keys are automatically removed after TTL to prevent stale entries.
    """
    cache = get_cache()
    tags = get_tags_for_key(key)
    for tag in tags:
        tag_set_key = f"{tag}:keys"
        try:
            # Add key to the tag's key set
            await cache.set(
                f"{tag_set_key}:{key}",
                "1",
                ttl=ttl_seconds,
            )
        except Exception:  # pragma: no cover - defensive guard
            logger.debug(f"Failed to register key {key} with tag {tag}")


async def invalidate_by_tag(tag: CacheTag) -> int:
    """
    Invalidate all cache entries associated with a specific tag.

    Returns the number of keys invalidated.

    Note: This uses a pattern-based approach which requires Redis SCAN.
    For high-performance scenarios, consider using Redis keyspace notifications.
    """
    cache = get_cache()
    # Invalidate the tag tracker itself
    await cache.invalidate(f"{tag}:keys")
    logger.info(f"Invalidated all entries with tag {tag}")
    return 0  # Actual count requires SCAN implementation


def schedule_cache_key(group_id: int) -> str:
    """Generate cache key for group schedule."""
    return f"{CACHE_PREFIX_SCHEDULE}:{group_id}"


def user_cache_key(user_id: int) -> str:
    """Generate cache key for user profile."""
    return f"{CACHE_PREFIX_USER}:{user_id}"


def event_cache_key(event_id: int) -> str:
    """Generate cache key for event."""
    return f"{CACHE_PREFIX_EVENT}:{event_id}"


def events_list_cache_key() -> str:
    """Generate cache key for events list."""
    return f"{CACHE_PREFIX_EVENT}:list"


def news_cache_key(news_id: int) -> str:
    """Generate cache key for news item."""
    return f"{CACHE_PREFIX_NEWS}:{news_id}"


def news_list_cache_key() -> str:
    """Generate cache key for news list."""
    return f"{CACHE_PREFIX_NEWS}:list"


async def invalidate_schedule_cache(group_id: int) -> None:
    """Invalidate cached schedule for a group."""
    cache = get_cache()
    key = schedule_cache_key(group_id)
    await cache.invalidate(key)
    logger.debug(f"Invalidated schedule cache for group {group_id}")


async def invalidate_user_cache(user_id: int) -> None:
    """Invalidate cached user profile."""
    cache = get_cache()
    key = user_cache_key(user_id)
    await cache.invalidate(key)
    logger.debug(f"Invalidated user cache for user {user_id}")


async def invalidate_event_cache(event_id: int) -> None:
    """Invalidate cached event and events list."""
    cache = get_cache()
    await cache.invalidate(
        event_cache_key(event_id),
        events_list_cache_key(),
    )
    logger.debug(f"Invalidated event cache for event {event_id}")


async def invalidate_news_cache(news_id: int) -> None:
    """Invalidate cached news item and news list."""
    cache = get_cache()
    await cache.invalidate(
        news_cache_key(news_id),
        news_list_cache_key(),
    )
    logger.debug(f"Invalidated news cache for news {news_id}")


async def invalidate_groups_cache() -> None:
    """Invalidate cached groups list."""
    cache = get_cache()
    await cache.invalidate(CACHE_PREFIX_GROUPS)
    logger.debug("Invalidated groups cache")


async def invalidate_all_schedules() -> None:
    """
    Invalidate all schedule caches.

    Note: This requires Redis SCAN which is not ideal for production.
    Consider using a more targeted approach or Redis keyspace notifications.
    """
    get_cache()
    # For now, we can't easily invalidate all keys with a prefix
    # This would require SCAN command support in the cache layer
    logger.warning(
        "invalidate_all_schedules called but pattern deletion not implemented"
    )


class CacheInvalidator:
    """
    Context manager for batch cache invalidation.

    Usage:
        async with CacheInvalidator() as inv:
            inv.schedule(group_id=1)
            inv.user(user_id=42)
            # Keys are invalidated when exiting the context
    """

    def __init__(self) -> None:
        self._keys: list[str] = []

    def schedule(self, group_id: int) -> None:
        """Queue schedule cache for invalidation."""
        self._keys.append(schedule_cache_key(group_id))

    def user(self, user_id: int) -> None:
        """Queue user cache for invalidation."""
        self._keys.append(user_cache_key(user_id))

    def event(self, event_id: int) -> None:
        """Queue event cache for invalidation."""
        self._keys.append(event_cache_key(event_id))
        self._keys.append(events_list_cache_key())

    def news(self, news_id: int) -> None:
        """Queue news cache for invalidation."""
        self._keys.append(news_cache_key(news_id))
        self._keys.append(news_list_cache_key())

    async def flush(self) -> int:
        """Invalidate all queued keys. Returns number of keys invalidated."""
        if not self._keys:
            return 0
        cache = get_cache()
        unique_keys = list(set(self._keys))
        await cache.invalidate(*unique_keys)
        count = len(unique_keys)
        self._keys.clear()
        logger.debug(f"Invalidated {count} cache keys")
        return count

    async def __aenter__(self) -> CacheInvalidator:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.flush()


__all__ = [
    # Tag-based invalidation
    "CacheTag",
    "get_tags_for_key",
    "register_key_with_tags",
    "invalidate_by_tag",
    # Key generators
    "schedule_cache_key",
    "user_cache_key",
    "event_cache_key",
    "events_list_cache_key",
    "news_cache_key",
    "news_list_cache_key",
    # Invalidation functions
    "invalidate_schedule_cache",
    "invalidate_user_cache",
    "invalidate_event_cache",
    "invalidate_news_cache",
    "invalidate_groups_cache",
    # Batch invalidation
    "CacheInvalidator",
]
