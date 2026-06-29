"""
Audit service for structured security event logging.

This module provides standardized logging for security-relevant events
with request correlation and component-specific log routing.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any, TypeVar

from app.core.config import settings
from app.core.observability import get_request_id
from app.models.logs import DataAccessLog
from app.repositories.audit_repository import AuditRepository

if TYPE_CHECKING:
    from uuid import UUID

    from fastapi import Request

    from app.core.protocols import AsyncDatabaseSession
    from app.schemas.dtos import DataAccessLogDTO

logger = logging.getLogger("app.audit")


class SecurityEvent(StrEnum):
    """Standardized security event types for audit logging."""

    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGOUT_REVOKED = "auth.logout.revoked"
    AUTH_REGISTER = "auth.register"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"  # nosec B105

    # MFA events
    MFA_ENROLL_START = "mfa.enroll.start"
    MFA_ENROLL_COMPLETE = "mfa.enroll.complete"
    MFA_VERIFY_SUCCESS = "mfa.verify.success"
    MFA_VERIFY_FAILURE = "mfa.verify.failure"
    MFA_DISABLE = "mfa.disable"
    MFA_RECOVERY_CODE_USED = "mfa.recovery_code.used"

    # Password events
    PASSWORD_CHANGE = "password.change"  # nosec B105
    PASSWORD_RESET_REQUEST = "password.reset.request"  # nosec B105
    PASSWORD_RESET_COMPLETE = "password.reset.complete"  # nosec B105

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

    def _redact_sensitive(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of data with sensitive fields redacted."""
        # Define keys that are likely to contain secrets or PII.
        sensitive_keys = {
            "password",
            "new_password",
            "old_password",
            "passcode",
            "otp",
            "code",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "email",
            "phone",
            "phone_number",
            "address",
            "full_name",
            "credit_card",
            "cvv",
            "ssn",
            "jwt",
            "credential",
            "api_key",
        }
        sensitive_suffixes = ("_token", "_secret", "_key", "_pwd", "_password")

        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()
            should_redact = key_lower in sensitive_keys or any(
                key_lower.endswith(suffix) for suffix in sensitive_suffixes
            )

            if should_redact:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_sensitive(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def log(
        self,
        event: str | SecurityEvent,
        request: Request | None = None,
        user_id: UUID | None = None,
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
            # RZ-05: Use getattr guard — request.client can be None on unix socket
            # transports or certain ASGI test clients (AttributeError at runtime).
            _client = getattr(request, "client", None)
            payload["ip"] = (
                _client.host if _client and hasattr(_client, "host") else None
            )
            payload["path"] = request.url.path
            payload["method"] = request.method

        if reason:
            payload["reason"] = reason

        payload.update(kwargs)

        # Remove None values for cleaner logs
        payload = {k: v for k, v in payload.items() if v is not None}

        # Redact sensitive fields before logging
        redacted_payload = self._redact_sensitive(payload)

        target_logger = self._select_logger(event_str)
        print(
            f"[AUDIT DEBUG] event={event_str} level={level} logger={target_logger.name} enabled={target_logger.isEnabledFor(level)} handlers={target_logger.handlers} propagate={target_logger.propagate}"
        )
        target_logger.log(
            level, json.dumps(redacted_payload, default=str), extra=redacted_payload
        )

    # Convenience methods for common security events

    def login_success(self, request: Request, user_id: UUID) -> None:
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

    def logout(self, request: Request, user_id: UUID) -> None:
        """Log user logout."""
        self.log(SecurityEvent.AUTH_LOGOUT, request, user_id)

    def mfa_failure(
        self, request: Request, user_id: UUID, reason: str = "invalid_code"
    ) -> None:
        """Log MFA verification failure."""
        self.log(
            SecurityEvent.MFA_VERIFY_FAILURE,
            request,
            user_id,
            reason=reason,
            level=logging.WARNING,
        )

    def access_denied(
        self, request: Request, user_id: UUID | None, reason: str
    ) -> None:
        """Log access denial."""
        self.log(
            SecurityEvent.ACCESS_DENIED,
            request,
            user_id,
            reason=reason,
            level=logging.WARNING,
        )

    def rate_limit_exceeded(
        self, request: Request, user_id: UUID | None = None
    ) -> None:
        """Log rate limit exceeded event."""
        self.log(
            SecurityEvent.RATE_LIMIT_EXCEEDED,
            request,
            user_id,
            level=logging.WARNING,
        )


# Singleton instance for convenience
audit_service = AuditService()


_F = TypeVar("_F", bound=Callable[..., Any])


def auditable(
    event: str | SecurityEvent,
    *,
    user_id_param: str | None = None,
    include_args: bool = False,
    include_result: bool = False,
) -> Callable[[_F], _F]:
    """Decorator to automatically log security audit events.

    This decorator simplifies service methods by removing manual audit.log calls.
    It expects the first argument to be 'self' (a service instance with an 'audit' attribute)
    and one of the arguments to be 'request' (FastAPI Request).
    """
    import functools
    import inspect

    @functools.cache
    def _get_signature(func: Callable[..., Any]) -> inspect.Signature:
        """Cache signature per decorated function — avoid per-request overhead (TD-02)."""
        return inspect.signature(func)

    from functools import wraps

    def decorator(func: _F) -> _F:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            request = kwargs.get("request")
            if not request:
                # Fallback: look in positional args using cached signature.
                bound_args = _get_signature(func).bind(self, *args, **kwargs)
                request = bound_args.arguments.get("request")

            # Find user_id if specified
            user_id = None
            if user_id_param:
                bound_args = _get_signature(func).bind(self, *args, **kwargs)
                user_val = bound_args.arguments.get(user_id_param)
                if user_val:
                    if hasattr(user_val, "id"):
                        user_id = user_val.id
                    else:
                        user_id = user_val

            try:
                result = await func(self, *args, **kwargs)

                # Log SUCCESS

                log_kwargs: dict[str, Any] = {}
                if include_args:
                    log_kwargs["args"] = kwargs
                if include_result:
                    # RZ-05: Redact the result string if it contains sensitive patterns
                    # before logging to prevent accidental PII leakage from model __str__.
                    res_str = str(result)
                    # Simple heuristic: if any sensitive key is in the result string,
                    # we might have a leak. For "Absolute Perfection", we ensure
                    # result is logged via the same redaction engine if it was a dict,
                    # but since it's a string, we at least scan for obvious tokens.
                    if (
                        any(
                            k in res_str.lower()
                            for k in ["password", "secret", "token", "jwt", "key"]
                        )
                        and "REDACTED" not in res_str
                    ):
                        log_kwargs["result"] = "***REDACTED_BY_SECURITY_POLICY***"
                    else:
                        log_kwargs["result"] = res_str

                # Use self.audit if available, else fallback to global audit_service
                auditor = getattr(self, "audit", audit_service)
                auditor.log(event, request=request, user_id=user_id, **log_kwargs)

                return result
            except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — audit decorator must not alter exception propagation (reviewed TD-27-04)
                # RZ-20-04: KEEP broad — audit decorator must not alter exception
                # propagation. Re-raises unconditionally.
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


# ============================================================================
# Secure Audit Service with HMAC Integrity
# ============================================================================


class SecureAuditService:
    """
    Service for creating and verifying audit logs with cryptographic integrity.

    Uses HMAC-SHA256 to sign audit log entries, providing tamper detection.
    """

    def __init__(
        self, signing_key: bytes | None = None, signing_keys: list[bytes] | None = None
    ):
        if signing_keys is None:
            if signing_key is not None:
                signing_keys = [signing_key]
            else:
                signing_keys = self._parse_signing_keys(settings.audit_log_secret)
        if not signing_keys:
            raise ValueError("AUDIT_LOG_SECRET must provide at least one signing key")
        self._signing_keys = signing_keys
        self._primary_key = signing_keys[0]

    @staticmethod
    def _parse_signing_keys(value: str) -> list[bytes]:
        keys = [part.strip() for part in value.split(",") if part.strip()]
        if not keys:
            raise ValueError("AUDIT_LOG_SECRET must not be empty")
        return [key.encode("utf-8") for key in keys]

    def _compute_signature(
        self, log: DataAccessLog | DataAccessLogDTO, *, key: bytes | None = None
    ) -> str:
        """Compute HMAC signature for an audit log entry."""
        data_parts = [
            str(log.id or ""),
            str(log.actor_user_id or ""),
            str(log.subject_user_id or ""),
            str(log.resource_type or ""),
            str(log.resource_id or ""),
            str(log.action or ""),
            str(log.ip_address or ""),
            (
                log.created_at.isoformat()
                if log.created_at
                else datetime.now(UTC).isoformat()
            ),
        ]
        data = "|".join(data_parts)
        signing_key = key or self._primary_key
        return hmac.new(signing_key, data.encode("utf-8"), sha256).hexdigest()

    def _find_valid_key(self, log: DataAccessLog | DataAccessLogDTO) -> bytes | None:
        """Return the signing key that matches the stored signature, if any."""
        if not log.signature:
            return None

        import rust_ext

        data_parts = [
            str(log.id or ""),
            str(log.actor_user_id or ""),
            str(log.subject_user_id or ""),
            str(log.resource_type or ""),
            str(log.resource_id or ""),
            str(log.action or ""),
            str(log.ip_address or ""),
            (
                log.created_at.isoformat()
                if log.created_at
                else datetime.now(UTC).isoformat()
            ),
        ]
        data = "|".join(data_parts)

        # Convert bytes keys to strings for the Rust extension
        keys_str = [k.decode("utf-8") for k in self._signing_keys]

        if rust_ext.verify_audit_signature(keys_str, data, str(log.signature)):
            # Find which exact key matched (needed for re-signing logic)
            # In a high-performance scenario, Rust handles the bulk check.
            # We only re-check manually if we need the specific key index.
            for signing_key in self._signing_keys:
                expected = self._compute_signature(log, key=signing_key)
                if hmac.compare_digest(str(log.signature), expected):
                    return signing_key
        return None

    async def create_log(
        self,
        db: AsyncDatabaseSession,
        *,
        actor_user_id: UUID | None = None,
        subject_user_id: UUID | None = None,
        resource_type: str,
        resource_id: str | None = None,
        action: str,
        context: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DataAccessLogDTO:
        """Create a signed audit log entry.

        The HMAC-SHA256 signature is computed from the fully-flushed DTO so that
        server-generated fields (id, created_at) are included in the digest, then
        written back to the DB row via repo.update().  This replaces the previous
        model_copy() + flush() pattern that left signature=NULL in all rows (RZ-06).
        """
        repo = AuditRepository(db)
        # Step 1: persist the row — repo.create() flush+refresh gives us the
        # server-assigned id and created_at used in the HMAC digest.
        log = await repo.create(
            {
                "actor_user_id": actor_user_id,
                "subject_user_id": subject_user_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "context": context,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )
        # Step 2: compute signature over the flushed DTO (id + created_at locked in).
        signature = self._compute_signature(log)
        # Step 3: write the signature back to the actual DB row.
        updated = await repo.update(log.id, {"signature": signature})
        return (
            updated
            if updated is not None
            else log.model_copy(update={"signature": signature})
        )

    def verify_integrity(self, log: DataAccessLog | DataAccessLogDTO) -> bool:
        """Verify the integrity of an audit log entry."""
        return self._find_valid_key(log) is not None

    def resign_log(self, log: DataAccessLog | DataAccessLogDTO) -> bool:
        """
        Re-sign an audit log entry with the primary key if needed.

        Returns True when the signature was updated.
        """
        valid_key = self._find_valid_key(log)
        if valid_key is None:
            return False
        primary_signature = self._compute_signature(log, key=self._primary_key)
        if not isinstance(log, DataAccessLog):
            # Cannot re-sign a frozen DTO in-place, caller should handle
            return False

        log.signature = primary_signature
        return True

    async def verify_batch(
        self, db: AsyncDatabaseSession, *, limit: int = 1000
    ) -> tuple[int, int, list[UUID]]:
        """Verify integrity of a batch of audit logs."""
        repo = AuditRepository(db)
        logs = await repo.list_logs(limit=limit)
        invalid_ids = [log.id for log in logs if not self.verify_integrity(log)]
        return len(logs), len(logs) - len(invalid_ids), invalid_ids


_secure_audit_service: SecureAuditService | None = None
_secure_audit_service_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01


def get_secure_audit_service() -> SecureAuditService:
    """Get or create the global secure audit service instance."""
    global _secure_audit_service
    if _secure_audit_service is not None:  # RZ-33-29: fast path — no lock after init
        return _secure_audit_service
    with _secure_audit_service_lock:  # RZ-33-29: slow path — double-checked locking
        if _secure_audit_service is None:
            _secure_audit_service = SecureAuditService()
        return _secure_audit_service


__all__ = [
    "AuditService",
    "SecureAuditService",
    "SecurityEvent",
    "audit_service",
    "get_secure_audit_service",
]
