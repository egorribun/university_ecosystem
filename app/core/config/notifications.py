from __future__ import annotations

import os
from functools import cached_property
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.core.logging import get_logger
from app.core.notification_contract import (
    CANONICAL_NOTIFICATION_TOPICS,
    canonicalize_notification_topic,
)

from .base import (
    _DEVELOPMENT_ENVIRONMENTS,
    BaseAppSettings,
    _coerce_str_list,
    _load_file_secret,
    _validate_positive_int,
)

_logger = get_logger(__name__)


def _validate_webpush_subject(value: str) -> str:
    from email.utils import parseaddr
    from urllib.parse import urlparse

    normalized = value.strip()
    if not normalized:
        raise ValueError("WEBPUSH_SUBJECT must not be empty")
    lower = normalized.lower()
    if lower.startswith("mailto:"):
        _, address = parseaddr(normalized[7:])
        if address and "@" in address:
            return f"mailto:{address.lower()}"
        raise ValueError("WEBPUSH_SUBJECT mailto: value must contain a valid email")
    parsed = urlparse(normalized)
    scheme = parsed.scheme.lower()
    if scheme not in {"https", "http"}:
        raise ValueError("WEBPUSH_SUBJECT URL must use https or http scheme")
    if not parsed.netloc:
        raise ValueError("WEBPUSH_SUBJECT URL must include a host")
    if scheme == "http":
        hostname = (parsed.hostname or "").lower()
        if hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError(
                "Insecure http scheme is only allowed for localhost testing"
            )
    return normalized


class NotificationSettings(BaseAppSettings):
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "none"
    smtp_starttls: bool = False
    mail_from: str = "no-reply@example.com"

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    notifications_scheduler_poll_seconds: int = 30
    notifications_scheduler_window_minutes: int = 6
    notifications_scheduler_max_backoff_seconds: int = 300
    notifications_scheduler_inline_enabled: bool = True
    notifications_worker_metrics_host: str = "0.0.0.0"  # nosec B104
    notifications_worker_metrics_port: int = 9101
    notifications_webpush_concurrency_limit: int = 10
    notifications_retention_days: int = 90
    notifications_retention_cleanup_interval_seconds: int = 86_400
    notifications_retention_batch_size: int = 500
    notification_queue_dead_letter_retention_days: int = 30
    notification_queue_dead_letter_cleanup_interval_seconds: int = 86_400
    notifications_queue_max_size: int = 1024
    notifications_queue_enqueue_timeout_seconds: float = 0.5
    notifications_queue_in_memory_only: bool = False
    notifications_queue_retry_base_seconds: float = 1.0
    notifications_allowed_push_topics: list[str] | str = Field(
        default_factory=lambda: list(CANONICAL_NOTIFICATION_TOPICS)
    )
    notifications_queue_max_attempts: int = 5

    # Outbox worker tuning (PERF-04)
    outbox_poll_interval_seconds: float = 5.0
    outbox_batch_size: int = 20
    outbox_max_retries: int = 5
    embedded_outbox_worker_enabled: bool = True

    # RZ-20-02 (audit 2026-03-24): Docker Secrets / K8s Secrets support.
    @field_validator("vapid_private_key", mode="before")
    @classmethod
    def _load_vapid_key(cls, v: str | None) -> str | None:
        return _load_file_secret("VAPID_PRIVATE_KEY_FILE", v)

    @field_validator("smtp_password", mode="before")
    @classmethod
    def _load_smtp_password(cls, v: str | None) -> str | None:
        return _load_file_secret("SMTP_PASSWORD_FILE", v)

    @field_validator("smtp_security", mode="before")
    @classmethod
    def _normalize_smtp_security(cls, value: str | None) -> str:
        normalized = (value or "none").strip().lower()
        if normalized not in {"none", "ssl", "starttls"}:
            raise ValueError("SMTP_SECURITY must be one of: none, ssl, starttls")
        return normalized

    @field_validator("smtp_user")
    @classmethod
    def _validate_smtp_user_security(cls, value: str, info: ValidationInfo) -> str:
        if not value:
            return value
        security = str(info.data.get("smtp_security") or "none").lower()
        environment = str(info.data.get("environment") or "production").lower()
        if security == "none" and environment not in _DEVELOPMENT_ENVIRONMENTS:
            _logger.warning(
                "SMTP_USER is configured while SMTP_SECURITY=none for ENVIRONMENT=%s. "
                "Use SMTP_SECURITY=starttls or SMTP_SECURITY=ssl for production.",
                environment or "production",
            )
            raise ValueError(
                "SMTP_USER cannot be used with SMTP_SECURITY=none outside "
                "development environments"
            )
        return value

    @model_validator(mode="after")
    def _require_encrypted_smtp_transport(self) -> NotificationSettings:
        environment = str(
            getattr(self, "environment", "")
            or os.environ.get("ENVIRONMENT", "development")
        ).lower()
        if (
            self.smtp_host.strip()
            and self.smtp_security == "none"
            and environment not in _DEVELOPMENT_ENVIRONMENTS
        ):
            raise ValueError(
                "SMTP_SECURITY must be starttls or ssl when SMTP_HOST is configured "
                "outside development environments"
            )
        return self

    @field_validator("notifications_allowed_push_topics", mode="before")
    @classmethod
    def _validate_notifications_allowed_push_topics(cls, value: Any) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in _coerce_str_list(value):
            candidate = canonicalize_notification_topic(item)
            if not candidate or candidate in seen:
                continue
            if candidate not in CANONICAL_NOTIFICATION_TOPICS:
                raise ValueError(f"Unknown notification topic: {item!r}")
            seen.add(candidate)
            normalized.append(candidate)
        if not normalized:
            raise ValueError(
                "NOTIFICATIONS_ALLOWED_PUSH_TOPICS must include at least one topic"
            )
        return normalized

    @field_validator("notifications_retention_batch_size")
    @classmethod
    def _validate_notifications_retention_batch_size(cls, value: int) -> int:
        return _validate_positive_int(
            int(value), label="NOTIFICATIONS_RETENTION_BATCH_SIZE"
        )

    @cached_property
    def WEBPUSH_SUBJECT(self) -> str:
        raw_subject = (self.vapid_subject or "").strip()
        if not raw_subject:
            return "mailto:no-reply@example.com"
        subject = _validate_webpush_subject(raw_subject)
        return subject

    @cached_property
    def notifications_allowed_push_topics_set(self) -> frozenset[str]:
        return frozenset(self.notifications_allowed_push_topics)

    @cached_property
    def notifications_allowed_push_topics_list(self) -> list[str]:
        return list(self.notifications_allowed_push_topics)

    @cached_property
    def VAPID_PUBLIC_KEY(self) -> str:
        return self.vapid_public_key

    @cached_property
    def VAPID_PRIVATE_KEY(self) -> str:
        return self.vapid_private_key
