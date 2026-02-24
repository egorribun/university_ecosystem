import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from app.core.protocols import AsyncDatabaseSession

from app.api.validation import raise_forbidden
from app.auth.fingerprint import (
    SessionFingerprint,
    extract_fingerprint,
    get_suspicious_activity_detector,
)
from app.core.config import settings
from app.models.models import ActiveSession, User

logger = logging.getLogger("app.auth.security")


class AuthFingerprintService:
    def __init__(self, request: Request, locale: str):
        self.request = request
        self.locale = locale

    async def validate_fingerprint(
        self,
        user: User,
        session: ActiveSession,
        db: AsyncDatabaseSession,
        redis_service: Any = None,
    ) -> None:
        if not session.fingerprint_hash:
            return

        current_fp = extract_fingerprint(self.request)
        stored_fp = SessionFingerprint(
            user_agent=str(session.user_agent or ""),
            accept_language=str(session.accept_language or ""),
            ip_address=str(session.ip_address or ""),
            fingerprint_hash=str(session.fingerprint_hash or ""),
        )

        if current_fp.fingerprint_hash != stored_fp.fingerprint_hash:
            detector = get_suspicious_activity_detector()
            event = detector.check_fingerprint_mismatch(
                user_id=user.id,
                session_id=session.id,
                stored_fingerprint=stored_fp,
                current_fingerprint=current_fp,
            )

            if event:
                logger.warning(
                    "Session fingerprint mismatch detected — revoking session immediately",
                    extra=event.to_log_record(),
                )

                # Check environment to avoid accidental lockout in local dev/tests unless forced
                env = os.getenv("ENVIRONMENT") or getattr(
                    settings, "ENVIRONMENT", "production"
                )
                if env != "testing":
                    session.revoked_at = datetime.now(UTC)
                    await db.commit()

                    if redis_service:
                        try:
                            await redis_service.revoke_session(session.jti)
                        except Exception as e:
                            logger.error(f"Failed to revoke session in Redis: {e}")

                    raise_forbidden(self.locale, "errors.auth.session_compromised")
