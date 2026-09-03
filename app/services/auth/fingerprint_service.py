from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from redis.exceptions import RedisError

from app.api.validation import raise_forbidden
from app.auth.fingerprint import (
    SessionFingerprint,
    extract_fingerprint,
    get_suspicious_activity_detector,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.models import ActiveSession, User

logger = get_logger(__name__)


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

        # Accept-Language is controlled by the application's locale selector
        # for API calls but by the browser for document/SSR requests. It is
        # useful telemetry, not a stable authentication signal. Keep the
        # fail-closed revocation boundary on a non-empty User-Agent change.
        if stored_fp.user_agent and hmac.compare_digest(
            current_fp.user_agent, stored_fp.user_agent
        ):
            return
        if current_fp.fingerprint_hash != stored_fp.fingerprint_hash:
            detector = get_suspicious_activity_detector()
            event = detector.check_fingerprint_mismatch(
                user_id=user.id,
                session_id=session.id,
                stored_fingerprint=stored_fp,
                current_fingerprint=current_fp,
            )

            if event:
                # FIX-44-03: Log actual values for debugging header mismatches.
                logger.warning(
                    "Session fingerprint mismatch detected — revoking session immediately "
                    "(stored_al=%r, current_al=%r, stored_ua_len=%d, current_ua_len=%d)",
                    stored_fp.accept_language,
                    current_fp.accept_language,
                    len(stored_fp.user_agent),
                    len(current_fp.user_agent),
                    extra=event.to_log_record(),
                )

                # Check environment to avoid accidental lockout in local dev/tests unless forced
                env = os.getenv("ENVIRONMENT") or getattr(
                    settings, "ENVIRONMENT", "production"
                )
                # FIX-44-03: Skip revocation in development — Docker proxy layers
                # can cause subtle header differences (Accept-Language normalization).
                # Production retains full fingerprint enforcement.
                if env not in ("testing", "development"):
                    session.revoked_at = datetime.now(UTC)
                    if redis_service is None:
                        from app.services.auth.redis_session import RedisSessionService

                        redis_service = RedisSessionService()
                    try:
                        await redis_service.revoke_session(
                            session.jti, expires_at=session.expires_at
                        )
                    except (RedisError, RuntimeError, OSError):
                        await db.rollback()
                        raise
                    await db.commit()

                    raise_forbidden(self.locale, "errors.auth.session_compromised")
