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
    create_notifications_for_users,
    deliver_and_process_push_results,
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
    # Core utilities
    "_build_delivery_row",
    "_coerce_optional_text",
    "_ensure_aware",
    "_fetch_active_user_ids",
    "_normalize_translation_map",
    "_plain_text",
    # Scheduler
    "_scheduler_loop",
    # Stats
    "aggregate_notification_delivery_stats",
    "async_session",
    # Schedule reminders
    "build_schedule_reminder_message",
    # Cleanup
    "cleanup_stale_notifications",
    "create_notifications_for_users",
    "deliver_and_process_push_results",
    # Internal module re-exports for test patching
    "dt",
    "generate_schedule_reminders",
    # Quiet hours
    "is_user_in_quiet_hours",
    # News & Events
    "notify_about_event",
    "notify_about_news",
    "only_active_users",
    "prepare_push_payload_for_user",
    "send_web_push",
    "start_notifications_scheduler",
]
