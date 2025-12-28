"""
Feature flags system for safe incremental rollouts.

Provides a simple in-memory feature flag system with support for
percentage rollouts, user targeting, and environment-based defaults.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class FlagStatus(StrEnum):
    """Feature flag status."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PERCENTAGE = "percentage"


@dataclass
class FeatureFlag:
    """Feature flag definition."""

    name: str
    status: FlagStatus = FlagStatus.DISABLED
    description: str = ""
    percentage: int = 0  # 0-100 for percentage rollouts
    allowed_users: set[int] = field(default_factory=set)
    allowed_groups: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_enabled_for_user(self, user_id: int | None = None) -> bool:
        """Check if flag is enabled for a specific user."""
        if self.status == FlagStatus.ENABLED:
            return True
        if self.status == FlagStatus.DISABLED:
            return False

        # Check user allowlist
        if user_id is not None and user_id in self.allowed_users:
            return True

        # Percentage rollout based on user_id hash
        if self.status == FlagStatus.PERCENTAGE and user_id is not None:
            return self._check_percentage(user_id)

        return False

    def _check_percentage(self, user_id: int) -> bool:
        """Determine if user falls within percentage rollout."""
        # Create deterministic hash from flag name + user_id
        hash_input = f"{self.name}:{user_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
        user_bucket = hash_value % 100
        return user_bucket < self.percentage


class FeatureFlagService:
    """
    Service for managing feature flags.

    Supports in-memory flags with optional database backing.
    """

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    def register(self, flag: FeatureFlag) -> None:
        """Register a feature flag."""
        self._flags[flag.name] = flag
        logger.debug("Registered feature flag: %s", flag.name)

    def get(self, name: str) -> FeatureFlag | None:
        """Get a feature flag by name."""
        return self._flags.get(name)

    def is_enabled(
        self,
        name: str,
        user_id: int | None = None,
        default: bool = False,
    ) -> bool:
        """
        Check if a feature flag is enabled.

        Args:
            name: Flag name
            user_id: Optional user ID for targeting
            default: Default value if flag not found

        Returns:
            True if feature is enabled, False otherwise
        """
        flag = self._flags.get(name)
        if flag is None:
            logger.debug("Unknown feature flag: %s, using default: %s", name, default)
            return default

        return flag.is_enabled_for_user(user_id)

    def list_flags(self) -> list[FeatureFlag]:
        """List all registered flags."""
        return list(self._flags.values())

    def enable(self, name: str) -> bool:
        """Enable a flag globally."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.ENABLED
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a flag globally."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.DISABLED
            return True
        return False

    def set_percentage(self, name: str, percentage: int) -> bool:
        """Set percentage rollout for a flag."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.PERCENTAGE
            flag.percentage = max(0, min(100, percentage))
            return True
        return False


# Global feature flag service instance
feature_flags = FeatureFlagService()

# Register default feature flags
feature_flags.register(
    FeatureFlag(
        name="new_dashboard",
        status=FlagStatus.DISABLED,
        description="New dashboard UI redesign",
    )
)

feature_flags.register(
    FeatureFlag(
        name="websocket_v2",
        status=FlagStatus.DISABLED,
        description="WebSocket protocol v2 with improved reconnection",
    )
)

feature_flags.register(
    FeatureFlag(
        name="push_batching",
        status=FlagStatus.ENABLED,
        description="Batch push notification delivery",
    )
)


__all__ = [
    "FeatureFlag",
    "FeatureFlagService",
    "FlagStatus",
    "feature_flags",
]
