"""
Feature flags system for safe incremental rollouts.

Provides a simple in-memory feature flag system with support for
percentage rollouts, user targeting, and environment-based defaults.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

FEATURE_FLAGS_KEY = "feature_flags"
FEATURE_FLAGS_CHANNEL = "feature_flags_updates"


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

    def to_dict(self) -> dict[str, Any]:
        """Convert flag to dictionary for serialization."""
        d = asdict(self)
        d["allowed_users"] = list(self.allowed_users)
        d["allowed_groups"] = list(self.allowed_groups)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureFlag:
        """Create flag from dictionary."""
        data["allowed_users"] = set(data.get("allowed_users", []))
        data["allowed_groups"] = set(data.get("allowed_groups", []))
        if "status" in data and isinstance(data["status"], str):
            data["status"] = FlagStatus(data["status"])
        return cls(**data)


class UniversityFeatureProvider(AbstractProvider):
    """OpenFeature Provider for University Ecosystem. (MOD-6)

    Wraps the existing FeatureFlagService to provide a standardized API.
    """

    def __init__(self, service: FeatureFlagService) -> None:
        self._service = service

    def get_metadata(self) -> Metadata:
        return Metadata(name="UniversityFeatureProvider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        user_id = None
        if evaluation_context and evaluation_context.targeting_key:
            try:
                user_id = int(evaluation_context.targeting_key)
            except (ValueError, TypeError):
                pass

        is_enabled = self._service.is_enabled(flag_key, user_id=user_id, default=default_value)
        return FlagResolutionDetails(
            value=is_enabled,
            reason=Reason.STATIC,  # Simplified for now
        )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        # String flags can be stored in metadata if needed
        flag = self._service.get(flag_key)
        if flag and "value" in flag.metadata:
            return FlagResolutionDetails(value=str(flag.metadata["value"]))
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        flag = self._service.get(flag_key)
        if flag and "value" in flag.metadata:
            try:
                return FlagResolutionDetails(value=int(flag.metadata["value"]))
            except (ValueError, TypeError):
                pass
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        flag = self._service.get(flag_key)
        if flag and "value" in flag.metadata:
            try:
                return FlagResolutionDetails(value=float(flag.metadata["value"]))
            except (ValueError, TypeError):
                pass
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Any,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[Any]:
        flag = self._service.get(flag_key)
        if flag and "value" in flag.metadata:
            return FlagResolutionDetails(value=flag.metadata["value"])
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)


class FeatureFlagService:
    """
    Service for managing feature flags.

    Supports in-memory flags with optional Redis persistence and Pub/Sub sync.
    """

    def __init__(self) -> None:
        # L1: In-memory cache
        self._flags: dict[str, FeatureFlag] = {}
        # Hardcoded defaults (will be used if Redis is empty or fails)
        self._defaults: dict[str, FeatureFlag] = {}
        self._redis: Redis | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._is_initialized = False

    async def initialize(self, redis: Redis | None = None) -> None:
        """
        Initialize the service, loading current state from Redis.

        Args:
            redis: Redis client for persistence and Pub/Sub.
        """
        if self._is_initialized:
            return

        from redis.asyncio import Redis
        self._redis = redis or (
            Redis.from_url(settings.cache_redis_url, decode_responses=True)
            if settings.cache_redis_url
            else None
        )

        if self._redis:
            # 1. Load from Redis
            try:
                stored_flags = await self._redis.hgetall(FEATURE_FLAGS_KEY)  # type: ignore[misc]
                for name, data_str in stored_flags.items():
                    try:
                        data = json.loads(data_str)
                        flag = FeatureFlag.from_dict(data)
                        self._flags[name] = flag
                    except (json.JSONDecodeError, Exception) as e:
                        logger.error("Failed to parse flag %s from Redis: %s", name, e)
            except Exception as e:
                logger.error("Failed to load feature flags from Redis: %s", e)

            # 2. Start Pub/Sub listener
            self._pubsub_task = asyncio.create_task(self._listen_for_updates())

        # Ensure all registered defaults are present (merged or added)
        for name, default_flag in self._defaults.items():
            if name not in self._flags:
                self._flags[name] = default_flag
            else:
                # Merge: status and description might have changed in Redis,
                # but we keep defaults if they're missing.
                pass

        self._is_initialized = True

        # MOD-6: Set OpenFeature provider
        api.set_provider(UniversityFeatureProvider(self))
        self.of_client = api.get_client()

        logger.info("Feature flag service initialized (%d flags and OpenFeature)", len(self._flags))

    async def shutdown(self) -> None:
        """Shutdown the service."""
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
        if self._redis:
            # If we created our own client, we should close it.
            # But usually it's passed from lifespan.
            pass

    async def _listen_for_updates(self):
        """Listen for flag updates via Pub/Sub."""
        if not self._redis:
            return

        ps = self._redis.pubsub()
        await ps.subscribe(FEATURE_FLAGS_CHANNEL)

        try:
            async for message in ps.listen():
                if message["type"] == "message":
                    name = message["data"]
                    logger.debug("Received update for flag: %s", name)
                    await self._reload_flag(name)
        except asyncio.CancelledError:
            await ps.unsubscribe(FEATURE_FLAGS_CHANNEL)
            await ps.aclose()
        except Exception as e:
            logger.error("Error in feature flag Pub/Sub listener: %s", e)

    async def _reload_flag(self, name: str):
        """Reload a specific flag from Redis."""
        if not self._redis:
            return

        try:
            data_str = await self._redis.hget(FEATURE_FLAGS_KEY, name)  # type: ignore[misc]
            if data_str:
                data = json.loads(data_str)
                flag = FeatureFlag.from_dict(data)
                self._flags[name] = flag
            elif name in self._defaults:
                # If deleted from Redis, revert to default
                self._flags[name] = self._defaults[name]
            else:
                self._flags.pop(name, None)
        except Exception as e:
            logger.error("Failed to reload flag %s from Redis: %s", name, e)

    def register(self, flag: FeatureFlag) -> None:
        """Register a default feature flag (sync for startups)."""
        self._defaults[flag.name] = flag
        if flag.name not in self._flags:
            self._flags[flag.name] = flag
        logger.debug("Registered feature flag default: %s", flag.name)

    def is_enabled(
        self,
        name: str,
        user_id: int | None = None,
        default: bool = False,
    ) -> bool:
        """Check if a feature flag is enabled (uses L1 cache)."""
        flag = self._flags.get(name)
        if flag is None:
            return default
        return flag.is_enabled_for_user(user_id)

    def get(self, name: str) -> FeatureFlag | None:
        """Get a feature flag by name."""
        return self._flags.get(name)

    def enable(self, name: str) -> None:
        """Enable a feature flag (sync, in-memory only)."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.ENABLED

    def disable(self, name: str) -> None:
        """Disable a feature flag (sync, in-memory only)."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.DISABLED

    def set_percentage(self, name: str, percentage: int) -> None:
        """Set percentage rollout for a flag (sync, in-memory only)."""
        flag = self._flags.get(name)
        if flag:
            flag.status = FlagStatus.PERCENTAGE
            flag.percentage = max(0, min(100, percentage))

    async def update(self, name: str, **kwargs) -> bool:
        """
        Update a feature flag and persist to Redis.

        Args:
            name: Flag name
            **kwargs: FeatureFlag fields to update (status, percentage, etc.)
        """
        flag = self._flags.get(name)
        if not flag:
            return False

        # update L1
        for key, value in kwargs.items():
            if hasattr(flag, key):
                setattr(flag, key, value)

        # update L2 (Redis)
        if self._redis:
            try:
                await self._redis.hset(  # type: ignore[misc]
                    FEATURE_FLAGS_KEY, name, json.dumps(flag.to_dict())
                )
                # Broadcast update
                await self._redis.publish(FEATURE_FLAGS_CHANNEL, name)
            except Exception as e:
                logger.error("Failed to persist flag %s to Redis: %s", name, e)
                return False

        return True

    def list_flags(self) -> list[FeatureFlag]:
        """List all current flags (from L1)."""
        return list(self._flags.values())


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
        name="websocket_query_param_compat",
        status=FlagStatus.DISABLED,
        description="Temporary support for WebSocket token in query param",
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
