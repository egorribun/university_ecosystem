from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_audit_service,
    get_current_user,
    get_db,
    get_login_service,
    get_user_service,
)
from app.auth import constants, mfa
from app.auth.schemas import (
    LoginIn,
    LoginPasskeyStartIn,
    LoginPasskeyVerifyIn,
    MfaVerifyIn,
    PendingMfaResponse,
)
from app.auth.security import decode_token
from app.core.config import settings
from app.core.localization import resolve_locale, translate
from app.models.models import ActiveSession, User
from app.schemas.schemas import (
    SessionSigningKeyOut,
    TokenWithProfile,
    UserCreate,
    WebAuthnAuthenticationOptionsOut,
)
from app.services.audit_service import AuditService
from app.services.auth.login_service import LoginService
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger("app.auth.login")

router = APIRouter(tags=["auth"])


@router.post(
    "/login/passkey/start",
    response_model=WebAuthnAuthenticationOptionsOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_passkey_start(
    payload: LoginPasskeyStartIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
):
    normalized_email = payload.email.strip().lower()
    from sqlalchemy import func, select

    res = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = res.scalars().first()

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)

    start = time.perf_counter()
    from app.core.timing import ensure_minimum_time

    if not user or not user.is_active:
        webauthn_options = service.get_dummy_authentication_options()
        await ensure_minimum_time(start, settings.auth_min_response_time)
        return WebAuthnAuthenticationOptionsOut(
            publicKey=webauthn_options,
            challenge_token=secrets.token_urlsafe(48),
        )

    options = await service.get_authentication_options(user)
    challenge = await mfa.issue_challenge(
        db,
        user_id=user.id,
        challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH,
        payload={"options": options},
    )
    await db.commit()

    await ensure_minimum_time(start, settings.auth_min_response_time)

    audit.log(
        "auth.login.passkey_start",
        request,
        user_id=user.id,
        reason="issued",
        extra={"challenge_id": challenge.id},
    )

    return WebAuthnAuthenticationOptionsOut(
        publicKey=options,
        challenge_token=challenge.token,
    )


@router.post(
    "/login/passkey/verify",
    response_model=TokenWithProfile | PendingMfaResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_passkey_verify(
    payload: LoginPasskeyVerifyIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    login_service: LoginService = Depends(get_login_service),
):
    try:
        challenge = await mfa.get_challenge(
            db,
            token=payload.challenge_token,
            challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH,
            consume=True,
        )
        await db.commit()
    except HTTPException:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid challenge")

    # Re-fetch after commit
    user = await db.get(User, challenge.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)
    try:
        await service.verify_authentication(
            user,
            challenge.payload["options"],
            payload.webauthn_response,
        )
    except Exception as e:
        logger.warning(f"Passkey verification failed for user {user.id}: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passkey verification failed")

    return await login_service.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        mfa_completed=True,
        method=mfa.MFA_METHOD_WEBAUTHN,
    )


@router.post("/login", response_model=TokenWithProfile | PendingMfaResponse)
async def login(
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    trust_device: bool = Form(False),
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    login_service: LoginService = Depends(get_login_service),
):
    return await login_service.perform_login(
        email=form_data.username,
        password=form_data.password,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        trust_device=trust_device,
    )


@router.post("/login/json", response_model=TokenWithProfile | PendingMfaResponse)
async def login_json(
    payload: LoginIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    login_service: LoginService = Depends(get_login_service),
):
    return await login_service.perform_login(
        email=payload.email,
        password=payload.password,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        trust_device=payload.trust_device,
    )


@router.post("/mfa/verify", response_model=TokenWithProfile)
async def verify_mfa_challenge(
    payload: MfaVerifyIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    login_service: LoginService = Depends(get_login_service),
):
    challenge_type = None
    if payload.method == constants.MFA_METHOD_TOTP:
        challenge_type = constants.CHALLENGE_TYPE_TOTP_VERIFY
    elif payload.method == constants.MFA_METHOD_WEBAUTHN:
        challenge_type = constants.CHALLENGE_TYPE_WEBAUTHN_AUTH
    elif payload.method == constants.MFA_METHOD_RECOVERY_CODE:
        # Recovery code can be used for any auth challenge
        challenge_type = [
            constants.CHALLENGE_TYPE_TOTP_VERIFY,
            constants.CHALLENGE_TYPE_WEBAUTHN_AUTH,
        ]
    else:
        # Invalid method
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA method"
        )

    challenge, _ = await mfa.consume_challenge(
        db,
        challenge_token=payload.challenge_token,
        challenge_type=challenge_type,
        provided_code=payload.code,
        provided_webauthn_response=payload.webauthn_response,
        provided_method=payload.method,
    )

    user = await db.get(User, challenge.user_id)
    return await login_service.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        mfa_completed=True,
        method=challenge.challenge_type,
    )


@router.post("/register", dependencies=[Depends(sensitive_route_limit())])
async def register(
    user: UserCreate,
    request: Request,
    user_service: Annotated[Any, Depends(get_user_service)],
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    try:
        new_user = await user_service.register_user(user)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover
        await db.rollback()
        message = translate("errors.users.create_failed", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    return {"status": "ok", "id": new_user.id}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
):
    """Terminate the client session."""
    raw_token = request.cookies.get("access_token_v2")
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    payload = decode_token(raw_token) if raw_token else None
    jti = payload.get("jti") if payload else None
    if jti:
        res = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session = res.scalars().first()
        if session:
            now = datetime.now(UTC)
            session.revoked_at = session.revoked_at or now
            session.signing_key = secrets.token_urlsafe(32)
            await db.commit()

            audit.log(
                "auth.logout.revoked",
                request,
                user_id=session.user_id,
                reason="user_initiated",
            )

        # Revoke from Redis (Cache-Aside)
        from app.services.auth.redis_session import RedisSessionService

        redis_service = RedisSessionService()
        await redis_service.revoke_session(jti)

    LoginService.clear_access_token_cookie(response)
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
    return {"message": "Logged out successfully"}


@router.get("/session/signing-key", response_model=SessionSigningKeyOut)
async def get_session_signing_key(
    request: Request, _: User = Depends(get_current_user)
):
    session = getattr(request.state, "active_session", None)
    if session is None or not getattr(session, "signing_key", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate(
                "errors.sessions.signing_key_missing",
                locale=resolve_locale(request=request),
            ),
        )
    return SessionSigningKeyOut(signing_key=session.signing_key)
