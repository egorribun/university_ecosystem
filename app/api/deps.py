from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import raise_forbidden, raise_unauthorized
from app.auth import mfa
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.config import settings
from app.core.container import get_vector_service
from app.core.database import get_db, get_read_db
from app.core.localization import resolve_locale, translate
from app.models.models import ActiveSession, User
from app.models.user_loaders import (
    USER_AUTH_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.repositories.active_session_repository import ActiveSessionRepository
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.auth.fingerprint_service import AuthFingerprintService
from app.services.auth.security_service import AuthSecurityService
from app.services.auth.token_service import AuthTokenService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    locale = resolve_locale(request=request)

    # 1. Decode and Validate Token
    payload = AuthTokenService.extract_and_decode_token(request, token, locale)
    user_id, jti = AuthTokenService.validate_payload(payload, locale)

    # 2. Redis Session Check (Cache-Aside)
    from app.services.auth.redis_session import RedisSessionService

    redis_service = RedisSessionService()
    cached_session = await redis_service.get_session(jti)

    user: User | None = None
    session: ActiveSession | None = None

    if cached_session:
        # HIT: Fast path validation
        if cached_session["user_id"] != str(user_id):
            raise_unauthorized(locale, "errors.auth.credentials_invalid")

        await redis_service.update_last_seen(jti)
        user = await db.get(User, user_id, options=USER_AUTH_LOAD_OPTIONS)
        if not user or not user.is_active:
            raise_unauthorized(locale, "errors.auth.credentials_invalid")

    # 3. MISS or Fallback: Full DB Validation
    if not user:
        session_repo = ActiveSessionRepository(db)
        row = await session_repo.get_active_session_with_user(
            user_id, jti, load_options=list(USER_AUTH_LOAD_OPTIONS)
        )
        if not row:
            raise_unauthorized(locale, "errors.auth.credentials_invalid")
        user, session = row

        # Populate Redis (Cache-Aside)
        from app.auth.fingerprint import SessionFingerprint

        fp = SessionFingerprint(
            user_agent=str(session.user_agent or ""),
            ip_address=str(session.ip_address or ""),
            accept_language=str(session.accept_language or ""),
            fingerprint_hash=str(session.fingerprint_hash or ""),
        )
        await redis_service.create_session(
            jti=jti,
            user_id=user.id,
            fingerprint=fp,
            mfa_verified_at=session.mfa_verified_at,
        )

    # Ensure we have a session object (required for downstream logic)
    if not session:
        res_s = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session = res_s.scalars().first()
        if not session or session.revoked_at:
            raise_unauthorized(locale, "errors.auth.credentials_invalid")

    # 4. Security Lifecycle Validation
    security_service = AuthSecurityService(db, locale)
    security_service.validate_session_expiry(session)

    # 5. Fingerprint Validation
    fingerprint_service = AuthFingerprintService(request, locale)
    await fingerprint_service.validate_fingerprint(user, session, db, redis_service)

    # 6. Post-validation updates (MFA TTL, Last Seen sync)
    await security_service.handle_mfa_ttl(session)
    await security_service.sync_last_seen(session, cached_session=bool(cached_session))

    request.state.active_session = session
    return user


async def get_current_user_dto(
    user: Annotated[User, Depends(get_current_user)],
) -> UserDTO:
    """Return the current user as a DTO."""
    return UserDTO.model_validate(user)


async def get_current_user_auth_dto(
    user: Annotated[User, Depends(get_current_user)],
) -> UserAuthDTO:
    """Return the current user as an Auth DTO (includes sensitive fields)."""
    return UserAuthDTO.model_validate(user)


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
    """Dependency that ensures the current user is an admin via SpiceDB.

    Returns HTTP 503 when SpiceDB is unreachable (fail-closed) so that
    operations can distinguish authorization outages from permission denials.
    """
    try:
        is_admin_user = await checker.check_admin(str(user.id), user=user)
    except SpiceDBUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "authz_unavailable",
                "message": "Authorization service temporarily unavailable",
            },
        )
    if not is_admin_user:
        locale = resolve_locale(request=request)
        raise_forbidden(locale)
    return user


def _enforce_fresh_mfa(request: Request) -> None:
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    locale = resolve_locale(request=request)
    if session is None:
        raise_forbidden(locale)

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


def get_analytics_service() -> Any:
    from app.services.analytics import get_analytics_service

    return get_analytics_service()
