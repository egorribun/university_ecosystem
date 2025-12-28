"""
Configuration package for modular settings.

This package provides organized configuration modules that can be
composed together or used independently of the main config.py.

Usage:
    from app.config.database import DatabaseSettings
    from app.config.security import SecuritySettings
    from app.config.notifications import NotificationsSettings
"""

from app.config.database import DatabaseSettings
from app.config.notifications import NotificationsSettings
from app.config.security import SecuritySettings

__all__ = [
    "DatabaseSettings",
    "SecuritySettings",
    "NotificationsSettings",
]
