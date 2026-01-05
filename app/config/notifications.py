"""
Notifications configuration settings.

Extracted from main config.py for better organization.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class NotificationsSettings(BaseSettings):
    """Notification system configuration."""

    # VAPID for Web Push
    vapid_private_key: str | None = Field(
        default=None,
        description="VAPID private key for Web Push",
    )

    vapid_public_key: str | None = Field(
        default=None,
        description="VAPID public key for Web Push",
    )

    vapid_subject: str = Field(
        default="mailto:admin@university.edu",
        description="VAPID subject (mailto or URL)",
    )

    # Push notification settings
    push_batch_size: int = Field(
        default=100,
        description="Batch size for push notification delivery",
    )

    push_retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed push",
    )

    push_ttl_seconds: int = Field(
        default=86400,
        description="Time-to-live for push messages (24h default)",
    )

    # Notification retention
    notification_retention_days: int = Field(
        default=90,
        description="Days to retain notifications before cleanup",
    )

    # Schedule reminders
    schedule_reminder_minutes: int = Field(
        default=15,
        description="Minutes before class to send reminder",
    )

    # Quiet hours
    quiet_hours_start: int = Field(
        default=22,
        description="Start of quiet hours (24h format)",
    )

    quiet_hours_end: int = Field(
        default=7,
        description="End of quiet hours (24h format)",
    )

    class Config:
        env_prefix = ""
        extra = "ignore"

    @property
    def has_vapid_keys(self) -> bool:
        """Check if VAPID keys are configured."""
        return bool(self.vapid_private_key and self.vapid_public_key)


__all__ = ["NotificationsSettings"]
