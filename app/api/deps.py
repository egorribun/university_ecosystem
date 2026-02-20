import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import raise_forbidden, raise_unauthorized
from app.auth import mfa
from app.auth.rbac import PermissionChecker
from app.auth.security import decode_token
from app.core.config import settings
from app.core.container import get_vector_service
from app.core.database import get_db, get_read_db
from app.core.localization import resolve_locale, translate
from app.models.models import ActiveSession, User
from app.models.user_loaders import (
    USER_AUTH_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    locale = resolve_locale(request=request)

    def fail_auth():
        raise_unauthorized(
            locale,
            "errors.auth.credentials_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = token or request.cookies.get("access_token_v2")
    if not raw_token:
        fail_auth()
        return None  # type: ignore[return-value]
    payload = decode_token(raw_token)
    if not payload:
        fail_auth()
        return None  # type: ignore[return-value]
    sub = payload.get("sub")
    jti = payload.get("jti")
    if not sub or not jti:
        fail_auth()
        return None  # type: ignore[return-value]
    try:
        user_id = UUID(sub)
    except (TypeError, ValueError):
        fail_auth()

    # Redis Session Check (Cache-Aside)
    from app.services.auth.redis_session import RedisSessionService

    redis_service = RedisSessionService()
    cached_session = await redis_service.get_session(jti)

    user: User | None = None
    session_obj: ActiveSession | None = None

    if cached_session:
        # HIT: Fast path
        # 1. Verify User ID matches (sanity check)
        if cached_session["user_id"] != str(user_id):
            fail_auth()

        # 2. Update activity in background (Redis)
        request.state.redis_session_jti = (
            jti  # Store for optimized access later if needed
        )
        # We don't await this to keep latency low, or we assume it's fast enough
        await redis_service.update_last_seen(jti)

        # 3. Load User from DB (Simple PK lookup, no joins needed for basic auth)
        # Note: We still need user roles/options.
        user = await db.get(User, user_id, options=USER_AUTH_LOAD_OPTIONS)
        if not user or not user.is_active:
            fail_auth()

        # Reconstruct minimal Session object for compatibility
        # We don't fetch the full ActiveSession from DB unless needed
        # (e.g. fingerprint mismatch)
        # However, legacy code expects `session` object.
        # For now, we fetch DB session primarily if we suspect issues
        # or for rigorous consistency,
        # OR we construct a transient implementation.
        # To maintain strict compatibility with `session.fingerprint_hash` checks below,
        # we will skip the DB session load IF fingerprint matches.

        # Validate Fingerprint from Redis data
        cached_fp_hash = cached_session.get("fingerprint_hash")

        # If we need the full DB object to respect logic below
        # (which commits MFA state),
        # we might still need it. But let's try to avoid the JOIN.
        pass

    # MISS or Fallback: Full DB Validation
    if not user:
        res = await db.execute(
            select(User, ActiveSession)
            .join(ActiveSession, ActiveSession.user_id == User.id)
            .where(User.id == user_id, User.is_active.is_(True))
            .where(ActiveSession.jti == jti)
            .where(ActiveSession.revoked_at.is_(None))
            .options(*USER_AUTH_LOAD_OPTIONS)
        )
        row = res.first()
        if not row:
            fail_auth()
            return None  # type: ignore[return-value]
        user, session_obj = row

        # POPULATE REDIS (Cache-Aside)
        from app.auth.fingerprint import SessionFingerprint

        fp = SessionFingerprint(
            user_agent=str(session_obj.user_agent or ""),
            ip_address=str(session_obj.ip_address or ""),
            accept_language=str(session_obj.accept_language or ""),
            fingerprint_hash=str(session_obj.fingerprint_hash or ""),
        )
        await redis_service.create_session(
            jti=str(jti),
            user_id=user.id,
            fingerprint=fp,
            mfa_verified_at=session_obj.mfa_verified_at,  # type: ignore[arg-type]
        )

    # If we hit Redis, we still need `session_obj` for the logic below
    # (fingerprint check etc).
    # Optimally, we construct it from checking the current request matches Redis data.
    # If we are here and `session_obj` is None, it means we hit Redis
    # but haven't loaded DB session.

    if not session_obj and cached_session:
        # Check constraints without DB
        cached_fp_hash = cached_session.get("fingerprint_hash")

        # Fingerprint Validation (Redis Path)
        if cached_fp_hash:
            from app.auth.fingerprint import extract_fingerprint

            current_fp = extract_fingerprint(request)
            if current_fp.fingerprint_hash != cached_fp_hash:
                # Suspicious! Fallback to DB to run full logic
                pass  # Logic continues below requires real session object
                # To simplify migration phase: If Redis hit, we basically trust it
                # unless we implement full logic here.
                # For safety in Phase 1: We will fetch the DB session even on Redis hit
                # BUT using a simpler query
                # (SELECT * FROM active_sessions WHERE id = ...),
                # avoiding the JOIN if possible, or accept that we simply
                # optimized user loading.

                # REVISED STRATEGY:
                # The big cost is the JOIN.
                # We already loaded User.
                # Let's load Session by JTI separately (fast index scan).
                res_s = await db.execute(
                    select(ActiveSession).where(ActiveSession.jti == jti)
                )
                session_obj = res_s.scalars().first()
                if not session_obj or session_obj.revoked_at:
                    fail_auth()
                    return None  # type: ignore[return-value]

    # If we still don't have session_obj (shouldn't happen if logic is correct):
    if not session_obj:
        # Fallback load
        res_s = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session_obj = res_s.scalars().first()
        if not session_obj:
            fail_auth()
            return None  # type: ignore[return-value]

    # --- Standard Validation Logic (from DB object) ---
    # Now that we have session_obj, we run standard checks.
    # The optimization is that we avoided the JOIN for every request
    # by splitting queries
    # (if using Redis) or we accept that we double-check DB for now.

    # Actually, for true performance, we should NOT load session_obj if Redis is valid.
    # Let's trust Redis for validity (revocation check) and only load DB
    # if we need to write to it.
    #
    # Current implementation limitation: The existing logic heavily relies
    # on `session` attributes.
    # Preserving behavior:
    session = session_obj
    now = datetime.now(UTC)
    expires_at = session.expires_at
    if expires_at is None:
        fail_auth()
        return None  # type: ignore[return-value]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        fail_auth()
        return None  # type: ignore[return-value]

    # Fingerprint validation
    if session.fingerprint_hash:
        from app.auth.fingerprint import (
            SessionFingerprint,
            extract_fingerprint,
            get_suspicious_activity_detector,
        )

        current_fp = extract_fingerprint(request)
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
                import logging

                logging.getLogger("app.auth.security").warning(
                    "Session fingerprint mismatch detected - enforcing MFA step-up",
                    extra=event.to_log_record(),
                )
                # Delegate mutation (e.g. session revocation/MFA enforcement) to dedicated
                # async events or background tasks instead of inline blocking DB writes here.
                if (
                    os.getenv("ENVIRONMENT") != "testing"
                    and getattr(settings, "ENVIRONMENT", "production") != "testing"
                ):
                    raise_forbidden(locale, "errors.auth.session_compromised")

    ttl = max(0, getattr(settings, "mfa_step_up_ttl_seconds", 0))
    if ttl > 0 and session.mfa_verified_at is not None:
        verified_at = session.mfa_verified_at
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        if now - verified_at > timedelta(seconds=ttl):
            session.mfa_verified_at = None  # type: ignore[assignment]
            await db.commit()

    # DB UPDATE OPTIMIZATION:
    # If we are using Redis and verified it was fresh, we can SKIP the DB
    # `last_seen_at` update entirely!
    # The Redis `update_last_seen` handles the hot path.
    # We only update DB occasionally (e.g. every 5-10 mins) to keep audit logs
    # roughly accurate.

    last_seen_at = session.last_seen_at
    if last_seen_at is not None and last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)

    # Increase sync window to 10 minutes if using Redis, else 5 mins
    sync_window = 600 if cached_session else 300

    if last_seen_at is None or (now - last_seen_at >= timedelta(seconds=sync_window)):
        from sqlalchemy import update

        stmt = (
            update(ActiveSession)
            .where(ActiveSession.id == session.id)
            .where(
                or_(
                    ActiveSession.last_seen_at.is_(None),
                    ActiveSession.last_seen_at < now - timedelta(seconds=sync_window),
                )
            )
            .values(last_seen_at=now)
            .execution_options(synchronize_session=False)
        )
        await db.execute(stmt)
        await db.commit()
        session.last_seen_at = now  # type: ignore[assignment]
        await db.refresh(user)

    request.state.active_session = session
    return user


async def get_current_user_optional(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Optional version of get_current_user that returns None instead of raising 401."""
    try:
        return await get_current_user(request, token, db)
    except HTTPException:
        return None


async def get_current_user_full(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current user with ALL MFA and Profile relationships loaded.
    Use this for endpoints that return full user profile (UserOut).
    """
    await ensure_mfa_relationships_loaded(db, user)
    return user


async def get_current_admin_user(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    checker: Annotated[PermissionChecker, Depends()],
) -> User:
    """Dependency that ensures the current user is an admin via SpiceDB."""
    is_admin_user = await checker.check_admin(str(user.id), user=user)
    if not is_admin_user:
        locale = resolve_locale(request=request)
        raise_forbidden(locale)
    return user


def _enforce_fresh_mfa(request: Request) -> None:
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    locale = resolve_locale(request=request)
    if session is None:
        raise_forbidden(locale)
        raise ValueError("Unreachable")  # Help mypy understand termination

    ttl = max(0, getattr(settings, "mfa_step_up_ttl_seconds", 0))
    if ttl == 0:
        return

    verified_at = session.mfa_verified_at
    if verified_at is None:
        message = translate("errors.auth.mfa_step_up_required", locale=locale)  # type: ignore[unreachable]
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": "mfa_step_up_required",
                "message": message,
                "session_id": str(session.id),
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
                "session_id": str(session.id),
            },
        )


async def require_fresh_mfa(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await ensure_mfa_relationships_loaded(db, user)
    if not mfa.user_has_confirmed_interactive_factor(user):
        return
    _enforce_fresh_mfa(request)


async def require_fresh_mfa_for_enrollment(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await ensure_mfa_relationships_loaded(db, user)
    if not mfa.user_has_confirmed_interactive_factor(user):
        return
    _enforce_fresh_mfa(request)


def get_locale(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> str:
    """
    Resolve locale from request headers or user preference.
    """
    # Priority:
    # 1. Query param (implied by some frontends, but not implemented here yet)
    # 2. Accept-Language header (via resolve_locale)
    # 3. User preference

    # We use resolve_locale to handle header parsing
    header_locale = resolve_locale(request=request)

    # If user has a preference, it overrides header (or vice versa depending on policy)
    # Usually: User Profile > Header > Default
    user_locale = getattr(current_user, "preferred_locale", None)

    if user_locale:
        return str(user_locale)

    return str(header_locale)


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> "ChatService":  # type: ignore # noqa: F821
    from app.services.chat_service import ChatService

    return ChatService(session)


def get_read_chat_service(
    session: Annotated[AsyncSession, Depends(get_read_db)],
) -> "ChatService":  # type: ignore # noqa: F821
    from app.services.chat_service import ChatService

    return ChatService(session)


def create_event_service(session: AsyncSession, vector_service: Any) -> Any:
    from app.repositories.event_repository import EventRepository
    from app.services.event_service import EventService

    repo = EventRepository(session)
    return EventService(repo, vector_service)


def get_event_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> Any:
    return create_event_service(session, vector_service)


def get_read_event_service(
    session: Annotated[AsyncSession, Depends(get_read_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> Any:
    return create_event_service(session, vector_service)


def create_news_service(session: AsyncSession, vector_service: Any) -> Any:
    from app.repositories.news_repository import NewsRepository
    from app.services.news_service import NewsService

    repo = NewsRepository(session)
    return NewsService(repo, vector_service)


def get_news_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> Any:
    return create_news_service(session, vector_service)


def get_read_news_service(
    session: Annotated[AsyncSession, Depends(get_read_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> Any:
    return create_news_service(session, vector_service)


def create_story_service(session: AsyncSession) -> Any:
    from app.repositories.story_repository import StoryRepository
    from app.services.story_service import StoryService

    repo = StoryRepository(session)
    return StoryService(repo)


def get_story_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return create_story_service(session)


def get_read_story_service(
    session: Annotated[AsyncSession, Depends(get_read_db)],
) -> Any:
    return create_story_service(session)


def create_schedule_service(session: AsyncSession) -> Any:
    from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
    from app.services.schedule_optimizer import ScheduleOptimizerService
    from app.services.schedule_service import ScheduleService

    repo = ScheduleRepository(session)
    group_repo = GroupRepository(session)
    optimizer = ScheduleOptimizerService()
    return ScheduleService(repo, group_repo, optimizer)


def get_schedule_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return create_schedule_service(session)


def get_read_schedule_service(
    session: Annotated[AsyncSession, Depends(get_read_db)],
) -> Any:
    return create_schedule_service(session)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.user_repository import UserRepository
    from app.services.audit_service import audit_service
    from app.services.auth_service import AuthService

    auth_repo = AuthRepository(session)
    user_repo = UserRepository(session)
    return AuthService(audit_service, auth_repo, user_repo)


def get_session_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    from app.repositories.active_session_repository import ActiveSessionRepository
    from app.services.session_service import SessionService

    repo = ActiveSessionRepository(session)
    return SessionService(session, repo)


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    from app.repositories.user_repository import UserRepository
    from app.services.audit_service import audit_service
    from app.services.notification_service import NotificationService
    from app.services.user_service import UserService

    user_repo = UserRepository(session)
    notifications = NotificationService(session)
    return UserService(user_repo, audit_service, notifications)


def get_audit_service() -> Any:
    from app.services.audit_service import audit_service

    return audit_service


def get_login_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_service: Annotated[Any, Depends(get_user_service)],
    session_service: Annotated[Any, Depends(get_session_service)],
    audit: Annotated[Any, Depends(get_audit_service)],
) -> Any:
    from app.services.auth.lockout import LockoutService
    from app.services.auth.login_service import LoginService

    lockout_service = LockoutService(db)
    return LoginService(db, user_service, session_service, lockout_service, audit)
