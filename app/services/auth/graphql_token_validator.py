"""GraphQL token validator — REST-equivalent security for GraphQL requests.

Addresses the auth parity gap (P1, audit 2026-02-26) between the GraphQL path
and the REST ``get_current_user`` dependency (``app/api/deps/auth.py``).

The REST path enforces these security layers (the MFA-epoch policy is shared
through ``app.services.auth.session_policy``):
  1. Mandatory dedicated Redis JTI revocation check (outage fails closed)
  2. DB session revocation check             (fail-closed on DB error)
  3. Session expiry validation               (fail-closed)
  4. Fingerprint validation                  (revokes session on mismatch)
  5. User existence / is_active check        (fail-closed)
  6. MFA epoch: sessions older than the last MFA change are rejected

The original GraphQL ``get_context`` only performed steps 1 and a partial step 2
(no expiry check, no fingerprint validation). This service closes that gap so both
paths enforce identical security guarantees.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.revocation import get_revocation_redis_client
from app.core.logging import get_logger
from app.models import ActiveSession, User
from app.services.auth.session_policy import session_epoch_is_current

logger = get_logger(__name__)


class GraphQLTokenValidator:
    """Performs full REST-equivalent token validation for a GraphQL request.

    Usage inside ``schema.get_context``::

        validator = GraphQLTokenValidator(request, session)
        current_user = await validator.validate(user_id_str, jti)
        # None  → token invalid/revoked/expired; treat request as unauthenticated
        # User  → authenticated user object
    """

    def __init__(self, request: Request, session: AsyncSession) -> None:
        self._request = request
        self._session = session

    async def validate(self, user_id_str: str, jti: str) -> User | None:
        """Validate token claims and return the authenticated User, or None.

        Mirrors ``app/api/deps/auth.py`` (``_resolve_current_user``); the shared
        session policy lives in ``app.services.auth.session_policy``.
        """
        # Step 1 — mandatory durable revocation check; do not trust a possibly
        # stale DB row when tombstone verification is unavailable.
        if not await self._redis_jti_check(jti):
            return None

        # Step 2 — DB authoritative session load + revocation check (fail-closed)
        active_session = await self._load_db_session(jti)
        if active_session is None:
            return None

        # Step 3 — Session expiry (fail-closed)
        if not self._check_expiry(active_session):
            return None

        # Step 4 — User existence + is_active (fail-closed)
        user = await self._load_user(user_id_str)
        if user is None or not user.is_active:
            return None

        # Step 4b — MFA epoch: sessions minted before the last MFA change are dead
        # (same policy as REST via app.services.auth.session_policy).
        if not session_epoch_is_current(active_session.mfa_epoch, user.mfa_epoch):
            return None

        # Step 5 — Fingerprint validation (revokes session on mismatch, fail-closed)
        if not await self._check_fingerprint(user, active_session):
            return None

        return user

    # ------------------------------------------------------------------ helpers

    async def _redis_jti_check(self, jti: str) -> bool:
        """Reject revoked JTIs and fail closed when durable state is unavailable."""
        try:
            _redis = await get_revocation_redis_client()
            if await _redis.exists(f"revoked:jti:{jti}"):
                logger.debug("GraphQL: session revoked in Redis")
                return False
        except (RedisError, RuntimeError, OSError):
            logger.warning("GraphQL session revocation verification unavailable")
            raise RuntimeError("Durable session revocation check unavailable") from None
        return True

    async def _load_db_session(self, jti: str) -> ActiveSession | None:
        """Load the active (non-revoked) session for the given JTI, or None."""
        try:
            result = await self._session.execute(
                select(ActiveSession).where(
                    ActiveSession.jti == jti,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            return result.scalar_one_or_none()
        except (OSError, ConnectionError) as exc:
            # RZ-20-04: Narrowed — fail-closed on infra fault (deny, don't accept).
            logger.warning(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                "GraphQL: DB session load failed; denying request: %s", exc
            )
            return None

    def _check_expiry(self, session: ActiveSession) -> bool:
        """Return False if the session has already expired."""
        from datetime import UTC, datetime

        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            logger.debug("GraphQL: session expired")
            return False
        return True

    async def _load_user(self, user_id_str: str) -> User | None:
        """Load the User by UUID string, or None on invalid UUID / not found."""
        try:
            val = (
                _uuid.UUID(user_id_str) if isinstance(user_id_str, str) else user_id_str
            )
            result = await self._session.execute(select(User).where(User.id == val))
            return result.scalar_one_or_none()
        except (ValueError, TypeError) as exc:
            logger.debug(
                "GraphQL: invalid subject claim: %s", exc
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return None

    async def _check_fingerprint(self, user: User, session: ActiveSession) -> bool:
        """Run fingerprint validation; return False if the session was revoked."""
        if not session.fingerprint_hash:
            # No fingerprint stored (e.g. old session) — skip validation.
            return True
        try:
            from app.services.auth.fingerprint_service import AuthFingerprintService
            from app.services.auth.redis_session import RedisSessionService

            fp_svc = AuthFingerprintService(self._request, "en")
            redis_svc = RedisSessionService()
            await fp_svc.validate_fingerprint(user, session, self._session, redis_svc)
            return True
        except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — fingerprint mismatch denies session (reviewed TD-27-04)
            # RZ-20-04: KEEP broad — raise_forbidden() raises HTTPException which
            # is the EXPECTED signal for fingerprint mismatch. We must catch all
            # exceptions here because the fingerprint service may raise HTTP 403
            # or any infra error — both result in session denial (fail-closed).
            logger.warning(
                "GraphQL: fingerprint mismatch for user=%s jti=%s — denying",
                user.id,
                session.jti,
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return False
