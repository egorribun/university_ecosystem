from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid as _uuid_mod
from datetime import UTC, datetime, timedelta
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.api.validation import raise_forbidden, raise_unauthorized
from app.auth import mfa
from app.auth.fingerprint import SessionFingerprint
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.config import settings
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import get_cache_client
from app.models import ActiveSession, User
from app.models.user_loaders import (
    USER_AUTH_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.repositories.active_session_repository import ActiveSessionRepository
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.auth.fingerprint_service import AuthFingerprintService
from app.services.auth.redis_session import RedisSessionService
from app.services.auth.security_service import AuthSecurityService
from app.services.auth.token_service import AuthTokenService

_logger = get_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_redis_session_service() -> RedisSessionService:
    """FastAPI Depends factory for RedisSessionService.

    RZ-04 (audit 2026-03-04): Constructing RedisSessionService() inline inside
    get_current_user() bypasses the application DI container — it cannot be
    overridden in tests, and its URL implicitly re-reads settings on every
    request.  A Depends factory makes the dependency explicit and overridable.
    """
    return RedisSessionService()


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncDatabaseSession, Depends(get_db)],
    # RZ-04: Default None keeps direct callers (unit tests) working.
    # FastAPI's Depends() always resolves this via get_redis_session_service()
    # in production; tests that call the function directly fall back to a
    # fresh instance, which is equivalent to the old inline construction.
    redis_service: Annotated[
        RedisSessionService | None, Depends(get_redis_session_service)
    ] = None,
) -> User:
    if redis_service is None:
        redis_service = get_redis_session_service()

    locale = resolve_locale(request=request)

    # 1. Extract Validated IDs from Gateway OR Decode Local Token
    x_user_id = request.headers.get("X-User-ID")
    x_session_id = request.headers.get("X-Session-ID")

    if x_user_id and x_session_id:
        # RZ-14-05: Verify gateway HMAC-SHA256 signature before trusting these headers.
        # The gateway signs "{user_id}:{session_id}" with INTERNAL_HMAC_SECRET and sets
        # X-Internal-Signature. Without this check, any service that can reach the backend
        # directly (SSRF, path smuggling, compromised gateway peer) can impersonate any user.
        #
        # Skip verification when INTERNAL_HMAC_SECRET is not configured (dev/single-node).
        # In production, set the same secret on both gateway and backend.
        _hmac_secret = settings.internal_hmac_secret
        if _hmac_secret:
            sig_header = request.headers.get("X-Internal-Signature", "")
            expected_sig = hmac.new(
                _hmac_secret.encode(),
                f"{x_user_id}:{x_session_id}".encode(),
                hashlib.sha256,
            ).hexdigest()
            if not secrets.compare_digest(expected_sig, sig_header):
                _logger.warning(
                    "X-Internal-Signature verification failed for X-User-ID=%s — "
                    "possible gateway bypass or missing INTERNAL_HMAC_SECRET on gateway",
                    x_user_id,
                )
                raise_unauthorized(locale, "errors.auth.credentials_invalid")
        else:
            # RZ-W19-08: fail-closed in production when HMAC secret is missing
            if getattr(settings, "environment", "production") == "production":
                _logger.critical(
                    "INTERNAL_HMAC_SECRET not set in production — rejecting gateway-trusted request"
                )
                raise_unauthorized(locale, "errors.auth.credentials_invalid")
            _logger.warning(
                "INTERNAL_HMAC_SECRET not configured — skipping gateway signature verification "
                "(acceptable in development only)"
            )

        try:
            user_id = _uuid_mod.UUID(x_user_id)
            jti = x_session_id
        except ValueError:
            raise_unauthorized(locale, "errors.auth.credentials_invalid")
    else:
        # Fallback tracking for direct backend access
        payload = AuthTokenService.extract_and_decode_token(request, token, locale)
        user_id, jti = AuthTokenService.validate_payload(payload, locale)

    # 2. JTI Revocation Fast-Path — optional O(1) pre-check before session lookup.
    # NOTE (RZ-3): The "revoked:jti:<jti>" key is reserved for future use as an
    # additional defense-in-depth layer.  The authoritative revocation check is
    # session.revoked_at in PostgreSQL, enforced in every code path below.
    # If Redis is unavailable the except branch falls through silently — the DB
    # check is the source of truth and will still deny revoked sessions.
    try:
        _redis = await get_cache_client()
        if await _redis.exists(f"revoked:jti:{jti}"):
            raise_unauthorized(locale, "errors.auth.credentials_invalid")
    except HTTPException:
        raise
    except (
        RuntimeError,
        ConnectionError,
        TimeoutError,
        OSError,
    ) as exc:  # RZ-22-01: narrowed — Redis/NullCache errors
        # Redis unavailable: fall through to DB revoked_at check below
        _logger.debug("Redis revoked-jti check failed: %s", exc)  # nosec B110
        pass

    # 3. Redis Session Check (Cache-Aside)
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

        # RZ-3: Use session_id stored in Redis cache for O(1) pk lookup instead
        # of a secondary WHERE-jti query on every cache-hit request.
        cached_sid = cached_session.get("session_id")
        if cached_sid:
            try:
                session = await db.get(ActiveSession, _uuid_mod.UUID(cached_sid))
            except ValueError, TypeError:  # RZ-28-01
                session = None
        if not session or session.revoked_at:
            # session_id missing/stale in old cache entries — fall through to DB
            res_s = await db.execute(
                select(ActiveSession).where(ActiveSession.jti == jti)
            )
            session = res_s.scalars().first()
            if not session or session.revoked_at:
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

        # Populate Redis (Cache-Aside) — include session_id to avoid N+1 on next HIT
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
            session_id=session.id,
        )

    # 4. Security Lifecycle Validation
    if session is None:
        raise_unauthorized(locale, "errors.auth.credentials_invalid")
    assert session is not None  # noqa: S101

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
    db: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> User | None:
    """Optional version of get_current_user that returns None instead of raising 401."""
    try:
        return await get_current_user(request, token, db)
    except HTTPException:
        return None


async def get_current_user_full(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> User:
    """
    Get current user with ALL MFA and Profile relationships loaded.
    Use this for endpoints that return full user profile (UserOut).
    """
    await ensure_mfa_relationships_loaded(db, user)
    return user


# TD-14-05 (audit 2026-03-18): Bridge FastAPI Depends() → Dishka-managed PermissionChecker.
#
# The SpiceDB gRPC channel lives at Scope.APP (singleton — opened once per process, shared
# across all requests via HTTP/2 multiplexing). The PermissionChecker wrapping it lives at
# Scope.REQUEST.  Route handlers that use `Depends(get_permission_checker)` get a fresh
# PermissionChecker per request backed by the reused singleton channel — no TCP+TLS overhead.
#
# This bridge function is @inject-decorated so Dishka resolves FromDishka[PermissionChecker]
# through its middleware-managed request scope, then returns a plain PermissionChecker that
# FastAPI can forward to route handlers via ordinary Depends().
@inject
async def get_permission_checker(
    checker: FromDishka[PermissionChecker],
) -> PermissionChecker:
    """FastAPI dependency that returns the Dishka-managed PermissionChecker.

    Use as:
        checker: PermissionChecker = Depends(get_permission_checker)
    """
    return checker


async def get_current_admin_user(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    checker: Annotated[PermissionChecker, Depends(get_permission_checker)],
) -> User:
    """Dependency that ensures the current user is an admin via SpiceDB."""
    try:
        is_admin_user = await checker.check_admin(str(user.id), user=user)
    except SpiceDBUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "authz_unavailable",
                "message": "Authorization service temporarily unavailable",
            },
        ) from None
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
    db: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> None:
    await ensure_mfa_relationships_loaded(db, user)
    if not mfa.user_has_confirmed_interactive_factor(user):
        return
    _enforce_fresh_mfa(request)
