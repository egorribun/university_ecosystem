from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth.redis_session import get_session_backend
from app.auth.security import decode_token
from app.core.config import settings
from app.core.database import get_db
from app.localization import resolve_locale, translate
from app.models.models import ActiveSession, User
from app.models.user_loaders import USER_MFA_LOAD_OPTIONS
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    locale = resolve_locale(request=request)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=translate("errors.auth.credentials_invalid", locale=locale),
        headers={"WWW-Authenticate": "Bearer"},
    )
    raw_token = token or request.cookies.get("access_token")
    if not raw_token:
        raise credentials_exception
    payload = decode_token(raw_token)
    if not payload:
        raise credentials_exception
    sub = payload.get("sub")
    jti = payload.get("jti")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise credentials_exception
    user = await db.get(User, user_id, options=USER_MFA_LOAD_OPTIONS)
    if not user or not user.is_active:
        raise credentials_exception
    if not jti:
        raise credentials_exception

    # Fast-path check in Redis session backend if enabled
    session_backend = await get_session_backend()
    if not await session_backend.is_session_valid(jti):
        # Even if not in Redis, we might want to check DB as a fallback
        # but for performance we can assume if it's supposed to be in Redis,
        # it should be there.
        # If session_storage_backend is "redis", then we trust Redis.
        if settings.session_storage_backend == "redis":
            raise credentials_exception

    res = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
    session = res.scalars().first()
    now = datetime.now(UTC)
    if not session or session.user_id != user.id:
        raise credentials_exception
    if session.revoked_at is not None:
        raise credentials_exception
    expires_at = session.expires_at
    if expires_at is None:
        raise credentials_exception
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise credentials_exception

    # Fingerprint validation for session binding (logs suspicious activity)
    if session.fingerprint_hash:
        from app.auth.fingerprint import (
            SessionFingerprint,
            extract_fingerprint,
            get_suspicious_activity_detector,
        )

        current_fp = extract_fingerprint(request)
        stored_fp = SessionFingerprint(
            user_agent=session.user_agent or "",
            accept_language=session.accept_language or "",
            ip_address=session.ip_address or "",
            fingerprint_hash=session.fingerprint_hash,
        )

        # Check for fingerprint mismatch (log but don't block)
        if current_fp.fingerprint_hash != stored_fp.fingerprint_hash:
            detector = get_suspicious_activity_detector()
            event = detector.check_fingerprint_mismatch(
                user_id=user.id,
                session_id=session.id,
                stored_fingerprint=stored_fp,
                current_fingerprint=current_fp,
            )
            if event:
                import logging

                logging.getLogger("app.auth.security").warning(
                    "Session fingerprint mismatch detected",
                    extra=event.to_log_record(),
                )

    ttl = max(0, getattr(settings, "mfa_step_up_ttl_seconds", 0))
    if ttl > 0 and session.mfa_verified_at is not None:
        verified_at = session.mfa_verified_at
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        if now - verified_at > timedelta(seconds=ttl):
            session.mfa_verified_at = None
            await db.commit()

    update_last_seen = False
    last_seen_at = session.last_seen_at
    if last_seen_at is None:
        update_last_seen = True
    else:
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        if now - last_seen_at >= timedelta(seconds=30):
            update_last_seen = True
    request.state.active_session = session
    if update_last_seen:
        session.last_seen_at = now
        await db.commit()
    return user


async def get_current_admin_user(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that ensures the current user is an admin."""
    if user.role != "admin":
        locale = resolve_locale(request=request)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=translate("errors.forbidden", locale=locale),
        )
    return user


def _enforce_fresh_mfa(request: Request) -> None:
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    locale = resolve_locale(request=request)
    if session is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=translate("errors.forbidden", locale=locale),
        )

    ttl = max(0, getattr(settings, "mfa_step_up_ttl_seconds", 0))
    if ttl == 0:
        return

    verified_at = session.mfa_verified_at
    if verified_at is None:
        message = translate("errors.auth.mfa_step_up_required", locale=locale)
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": "mfa_step_up_required",
                "message": message,
                "session_id": session.id,
            },
        )

    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    if now - verified_at > timedelta(seconds=ttl):
        message = translate("errors.auth.mfa_step_up_required", locale=locale)
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": "mfa_step_up_required",
                "message": message,
                "session_id": session.id,
            },
        )


def require_fresh_mfa(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    if not mfa.user_has_confirmed_interactive_factor(user):
        return
    _enforce_fresh_mfa(request)


def require_fresh_mfa_for_enrollment(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    if not mfa.user_has_confirmed_interactive_factor(user):
        return
    _enforce_fresh_mfa(request)


def get_audit_service() -> AuditService:
    return AuditService()


def get_user_service(
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> UserService:
    return UserService(audit)


def get_auth_service(
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthService:
    return AuthService(audit)
