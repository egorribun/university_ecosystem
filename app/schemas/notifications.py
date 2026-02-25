"""Pydantic schemas for push notification routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.localization import translate
from app.services.push_topics import normalize_topic, normalize_topics


class NotificationAction(BaseModel):
    action: str = Field(..., description="Notification action identifier")
    title: str = Field(..., description="Action button title")
    url: str | None = Field(default=None, description="Optional URL to open")
    icon: str | None = Field(default=None, description="Optional icon URL")

    @field_validator("action", "title", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


class NotifyBody(BaseModel):
    title: str
    body: str | None = None
    url: str | None = None
    tag: str | None = None
    badge: str | None = None
    type: str | None = None
    ttl: int | None = None
    urgency: str | None = "normal"
    topic: str | None = None
    actions: list[NotificationAction] | None = None
    data: dict[str, Any] | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, value: Any) -> Any:
        return normalize_topic(value)


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., description="Base64-encoded public key")
    auth: str = Field(..., description="Authentication secret")

    @field_validator("p256dh", "auth", mode="before")
    @classmethod
    def _ensure_not_blank(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(..., description="Push subscription endpoint URL")
    keys: PushSubscriptionKeys
    topics: list[str] | None = Field(
        default=None, description="Optional list of topics"
    )
    user_agent: str | None = Field(default=None, description="User agent override")

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_topics(value)


class PushSubscriptionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    endpoint: str
    p256dh: str
    auth: str
    created_at: datetime
    user_agent: str | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None
    topics: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("topics", mode="before")
    @classmethod
    def _topics_before(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, list):
            return normalize_topics(v)
        return []


class PushSubscriptionTopicsUpdate(BaseModel):
    endpoint: str
    topics: list[str] = Field(default_factory=list)

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        return normalize_topics(value)


class PushSubscriptionDelete(BaseModel):
    endpoint: str

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


class DisableUserPushRequest(BaseModel):
    user_id: uuid.UUID = Field(
        ...,
        description=translate("notifications.push.disable_user.description"),
    )


class PushTopicsResponse(BaseModel):
    allowed: list[str]
    topics: list[str]
    has_preferences: bool = False
    updated_at: datetime | None = None


class AdminUserTopicsUpdate(BaseModel):
    topics: list[str] = Field(default_factory=list)

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        return normalize_topics(value, strict=True)


class AdminUserTopicsResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    topics: list[str]
    allowed_topics: list[str]
    updated_at: datetime | None = None


class SendTestResponse(BaseModel):
    total: int = 0
    sent: int
    removed: int
    failed: int
    detail: str | None = None


class PushTestRequest(NotifyBody):
    user_id: uuid.UUID | None = Field(
        default=None, description="Target user id for testing"
    )
    title: str = Field(
        default=translate("notifications.push.test.title_default"),
        description="Notification title",
    )
    body: str | None = Field(
        default=translate("notifications.push.test.body_default"),
        description="Notification body",
    )
    url: str | None = Field(
        default=None, description="URL to open when clicking the notification"
    )
