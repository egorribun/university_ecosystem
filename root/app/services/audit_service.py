"""
Audit service for structured security event logging.

This module provides standardized logging for security-relevant events
with request correlation and component-specific log routing.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Any

from fastapi import Request

from app.core.observability import get_request_id

logger = logging.getLogger("app.audit")


class SecurityEvent(StrEnum):
    """Standardized security event types for audit logging."""

    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGOUT_REVOKED = "auth.logout.revoked"
    AUTH_REGISTER = "auth.register"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"

    # MFA events
    MFA_ENROLL_START = "mfa.enroll.start"
    MFA_ENROLL_COMPLETE = "mfa.enroll.complete"
    MFA_VERIFY_SUCCESS = "mfa.verify.success"
    MFA_VERIFY_FAILURE = "mfa.verify.failure"
    MFA_DISABLE = "mfa.disable"

    # Password events
    PASSWORD_CHANGE = "password.change"
    PASSWORD_RESET_REQUEST = "password.reset.request"
    PASSWORD_RESET_COMPLETE = "password.reset.complete"

    # User events
    USER_PROFILE_UPDATE = "users.profile.update"
    USER_EMAIL_CHANGE = "users.email.change"
    USER_AVATAR_UPLOAD = "users.avatar.upload"
    USER_DELETE = "users.delete"

    # Admin events
    ADMIN_USER_CREATE = "admin.user.create"
    ADMIN_USER_MODIFY = "admin.user.modify"
    ADMIN_USER_DELETE = "admin.user.delete"
    ADMIN_ROLE_CHANGE = "admin.role.change"

    # Access events
    ACCESS_DENIED = "access.denied"
    RATE_LIMIT_EXCEEDED = "access.rate_limit"


class AuditService:
    """Service for structured security event logging."""

    def __init__(self) -> None:
        self.logger = logger

    def _select_logger(self, event: str) -> logging.Logger:
        """Route audit events to component-specific loggers."""
        if event.startswith("auth."):
            return logging.getLogger("app.auth")
        if event.startswith(("password.", "users.")):
            return logging.getLogger("app.users.audit")
        if event.startswith("mfa."):
            return logging.getLogger("app.mfa")
        if event.startswith("admin."):
            return logging.getLogger("app.admin")
        if event.startswith("access."):
            return logging.getLogger("app.access")
        return self.logger

    def log(
        self,
        event: str | SecurityEvent,
        request: Request | None = None,
        user_id: int | None = None,
        level: int = logging.INFO,
        reason: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a security audit event with full context."""
        event_str = str(event)
        payload: dict[str, Any] = {
            "event": event_str,
            "user_id": str(user_id) if user_id else None,
            "request_id": get_request_id(),
        }

        if request:
            payload["ip"] = request.client.host if request.client else None
            payload["path"] = request.url.path
            payload["method"] = request.method

        if reason:
            payload["reason"] = reason

        payload.update(kwargs)

        # Remove None values for cleaner logs
        payload = {k: v for k, v in payload.items() if v is not None}

        target_logger = self._select_logger(event_str)
        target_logger.log(level, json.dumps(payload), extra=payload)

    # Convenience methods for common security events

    def login_success(self, request: Request, user_id: int) -> None:
        """Log successful login."""
        self.log(
            SecurityEvent.AUTH_LOGIN_SUCCESS, request, user_id, reason="authenticated"
        )

    def login_failure(
        self, request: Request, reason: str = "invalid_credentials"
    ) -> None:
        """Log failed login attempt."""
        self.log(
            SecurityEvent.AUTH_LOGIN_FAILURE,
            request,
            reason=reason,
            level=logging.WARNING,
        )

    def logout(self, request: Request, user_id: int) -> None:
        """Log user logout."""
        self.log(SecurityEvent.AUTH_LOGOUT, request, user_id)

    def mfa_failure(
        self, request: Request, user_id: int, reason: str = "invalid_code"
    ) -> None:
        """Log MFA verification failure."""
        self.log(
            SecurityEvent.MFA_VERIFY_FAILURE,
            request,
            user_id,
            reason=reason,
            level=logging.WARNING,
        )

    def access_denied(self, request: Request, user_id: int | None, reason: str) -> None:
        """Log access denial."""
        self.log(
            SecurityEvent.ACCESS_DENIED,
            request,
            user_id,
            reason=reason,
            level=logging.WARNING,
        )

    def rate_limit_exceeded(self, request: Request, user_id: int | None = None) -> None:
        """Log rate limit exceeded event."""
        self.log(
            SecurityEvent.RATE_LIMIT_EXCEEDED,
            request,
            user_id,
            level=logging.WARNING,
        )


# Singleton instance for convenience
audit_service = AuditService()


# ============================================================================
# Secure Audit Service with HMAC Integrity
# ============================================================================

import hmac
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.logs import DataAccessLog


class SecureAuditService:
    """
    Service for creating and verifying audit logs with cryptographic integrity.

    Uses HMAC-SHA256 to sign audit log entries, providing tamper detection.
    """

    def __init__(self, signing_key: bytes | None = None):
        if signing_key is None:
            signing_key = settings.secret_key.encode("utf-8")
        self._signing_key = signing_key

    def _compute_signature(self, log: DataAccessLog) -> str:
        """Compute HMAC signature for an audit log entry."""
        from datetime import UTC, datetime

        data_parts = [
            str(log.id or ""),
            str(log.actor_user_id or ""),
            str(log.subject_user_id or ""),
            log.resource_type or "",
            log.resource_id or "",
            log.action or "",
            log.ip_address or "",
            (
                log.created_at.isoformat()
                if log.created_at
                else datetime.now(UTC).isoformat()
            ),
        ]
        data = "|".join(data_parts)
        return hmac.new(self._signing_key, data.encode("utf-8"), sha256).hexdigest()

    async def create_log(
        self,
        db: AsyncSession,
        *,
        actor_user_id: int | None = None,
        subject_user_id: int | None = None,
        resource_type: str,
        resource_id: str | None = None,
        action: str,
        context: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DataAccessLog:
        """Create a signed audit log entry."""
        log = DataAccessLog(
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            context=context,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)
        await db.flush()
        log.signature = self._compute_signature(log)
        await db.flush()
        return log

    def verify_integrity(self, log: DataAccessLog) -> bool:
        """Verify the integrity of an audit log entry."""
        if not log.signature:
            return False
        expected = self._compute_signature(log)
        return hmac.compare_digest(log.signature, expected)

    async def verify_batch(
        self, db: AsyncSession, *, limit: int = 1000
    ) -> tuple[int, int, list[int]]:
        """Verify integrity of a batch of audit logs."""
        result = await db.execute(
            select(DataAccessLog)
            .where(DataAccessLog.signature.isnot(None))
            .order_by(DataAccessLog.created_at.desc())
            .limit(limit)
        )
        logs = list(result.scalars().all())
        invalid_ids = [log.id for log in logs if not self.verify_integrity(log)]
        return len(logs), len(logs) - len(invalid_ids), invalid_ids


_secure_audit_service: SecureAuditService | None = None


def get_secure_audit_service() -> SecureAuditService:
    """Get or create the global secure audit service instance."""
    global _secure_audit_service
    if _secure_audit_service is None:
        _secure_audit_service = SecureAuditService()
    return _secure_audit_service


__all__ = [
    "AuditService",
    "SecurityEvent",
    "audit_service",
    "SecureAuditService",
    "get_secure_audit_service",
]

