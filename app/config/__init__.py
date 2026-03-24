"""Legacy configuration package — DEPRECATED.

TD-20-03 (audit 2026-03-24): This module duplicated app.core.config and was
never imported from application code.  It now re-exports from the canonical
location for backward compatibility.  New code should import directly from
``app.core.config``.
"""

from app.core.config.database import DatabaseSettings
from app.core.config.notifications import NotificationSettings as NotificationsSettings
from app.core.config.security import SecuritySettings

__all__ = [
    "DatabaseSettings",
    "NotificationsSettings",
    "SecuritySettings",
]
