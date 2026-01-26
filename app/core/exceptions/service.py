"""Service-layer exception classes for typed error handling.

These exceptions provide fine-grained error classification for service operations,
enabling proper error recovery and structured logging without relying on broad
`except Exception:` handlers.
"""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Base exception for all service-layer errors.

    Provides structured error information with optional details dictionary
    for additional context. All service exceptions should inherit from this.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        self.__cause__ = cause
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r}, details={self.details!r})"


class ExternalServiceError(ServiceError):
    """Raised when an external API or service call fails.

    Use for:
    - Third-party API failures (e.g., HIBP, Spotify, email providers)
    - Timeout errors from external services
    - Network-related failures
    """

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if service_name:
            full_details["service_name"] = service_name
        if status_code is not None:
            full_details["status_code"] = status_code
        super().__init__(message, full_details, cause=cause)
        self.service_name = service_name
        self.status_code = status_code


class StorageError(ServiceError):
    """Raised when a storage operation fails.

    Use for:
    - S3/MinIO upload/download failures
    - Local filesystem errors
    - File processing errors
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        path: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if operation:
            full_details["operation"] = operation
        if path:
            full_details["path"] = path
        super().__init__(message, full_details, cause=cause)
        self.operation = operation
        self.path = path


class TokenError(ServiceError):
    """Raised when token operations fail.

    Use for:
    - JWT encoding/decoding failures
    - Token validation failures
    - Key rotation issues
    """

    def __init__(
        self,
        message: str,
        *,
        token_type: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if token_type:
            full_details["token_type"] = token_type
        if reason:
            full_details["reason"] = reason
        super().__init__(message, full_details, cause=cause)
        self.token_type = token_type
        self.reason = reason


class CacheError(ServiceError):
    """Raised when cache operations fail (generally non-critical).

    Use for:
    - Redis connection failures
    - Cache invalidation errors
    - Serialization failures

    Note: Cache errors are typically logged but not propagated to users,
    as the application should gracefully degrade to database reads.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        key: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if operation:
            full_details["operation"] = operation
        if key:
            full_details["key"] = key
        super().__init__(message, full_details, cause=cause)
        self.operation = operation
        self.key = key


class NotificationError(ServiceError):
    """Raised when notification delivery fails.

    Use for:
    - Push notification delivery failures
    - Email sending failures
    - WebSocket message failures
    """

    def __init__(
        self,
        message: str,
        *,
        notification_type: str | None = None,
        recipient_id: int | str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if notification_type:
            full_details["notification_type"] = notification_type
        if recipient_id is not None:
            full_details["recipient_id"] = recipient_id
        super().__init__(message, full_details, cause=cause)
        self.notification_type = notification_type
        self.recipient_id = recipient_id


class DatabaseError(ServiceError):
    """Raised when database operations fail beyond normal exceptions.

    Use for:
    - Connection pool exhaustion
    - Transaction failures that need special handling
    - Migration-related errors

    Note: Most database errors should propagate as SQLAlchemy exceptions.
    Use this only for application-level database error handling.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        table: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        full_details = details or {}
        if operation:
            full_details["operation"] = operation
        if table:
            full_details["table"] = table
        super().__init__(message, full_details, cause=cause)
        self.operation = operation
        self.table = table
