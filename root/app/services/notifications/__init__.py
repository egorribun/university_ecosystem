"""Notifications service package.

This package provides notification creation, delivery, and management
functionality for the university ecosystem platform.
"""

# Re-export the datetime module for monkeypatching in tests
import datetime as dt

from app.services.notifications.cleanup import cleanup_stale_notifications
from app.services.notifications.core import (
    _build_delivery_row,
    _coerce_optional_text,
    _ensure_aware,
    _fetch_active_user_ids,
    _normalize_translation_map,
    _plain_text,
    async_session,
)
from app.services.notifications.delivery import (
    _ensure_push_subscription_schema_once,
    create_notifications_for_users,
    invalidate_push_subscription_schema_cache,
    only_active_users,
    send_web_push,  # Re-exported from delivery for test compatibility
)
from app.services.notifications.news_events import (
    notify_about_event,
    notify_about_news,
)
from app.services.notifications.quiet_hours import (
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)
from app.services.notifications.schedule_reminders import (
    build_schedule_reminder_message,
    generate_schedule_reminders,
)
from app.services.notifications.scheduler import (
    _scheduler_loop,
    start_notifications_scheduler,
)
from app.services.notifications.stats import aggregate_notification_delivery_stats

__all__ = [
    # Internal module re-exports for test patching
    "dt",
    "send_web_push",
    # Core utilities
    "_build_delivery_row",
    "_coerce_optional_text",
    "_ensure_aware",
    "_fetch_active_user_ids",
    "_normalize_translation_map",
    "_plain_text",
    "async_session",
    # Cleanup
    "cleanup_stale_notifications",
    # Delivery
    "_ensure_push_subscription_schema_once",
    "create_notifications_for_users",
    "invalidate_push_subscription_schema_cache",
    "only_active_users",
    # News & Events
    "notify_about_event",
    "notify_about_news",
    # Quiet hours
    "is_user_in_quiet_hours",
    "prepare_push_payload_for_user",
    # Schedule reminders
    "build_schedule_reminder_message",
    "generate_schedule_reminders",
    # Scheduler
    "_scheduler_loop",
    "start_notifications_scheduler",
    # Stats
    "aggregate_notification_delivery_stats",
]
