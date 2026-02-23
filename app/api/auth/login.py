from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING, Annotated, Any

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
from sqlalchemy import func, select

from app.api.deps import (
    get_audit_service,
    get_current_user,
    get_db,
    get_login_service,
    get_user_service,
)
from app.auth import constants, mfa
from app.auth.handlers.logout import router as logout_router
from app.auth.schemas import (
    LoginIn,
    LoginPasskeyStartIn,
    LoginPasskeyVerifyIn,
    MfaVerifyIn,
    PendingMfaResponse,
)
from app.core.config import settings
from app.core.localization import resolve_locale, translate
from app.core.rate_limit import sensitive_route_limit
from app.core.timing import ensure_minimum_time
from app.services.webauthn import WebAuthnService
from app.models.models import User
from app.schemas.schemas import (
    SessionSigningKeyOut,
    TokenWithProfile,
    UserCreate,
    WebAuthnAuthenticationOptionsOut,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.audit_service import AuditService
    from app.services.auth.login_service import LoginService

logger = logging.getLogger("app.auth.login")


router = APIRouter(tags=["auth"])
router.include_router(logout_router)


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
    user_service: Annotated[Any, Depends(get_user_service)] = None,
):
    normalized_email = payload.email.strip().lower()

    if user_service is None:
        # Fallback if dependency injection fails/is overridden in test
        res = await db.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        )
        user = res.scalars().first()
    else:
        user = await user_service.get_user_by_email(normalized_email)

    service = WebAuthnService(db)

    start = time.perf_counter()
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

    service = WebAuthnService(db)
    try:
        payload_dict: dict = challenge.payload  # type: ignore[assignment]
        await service.verify_authentication(
            user,
            str(payload_dict.get("options", {}).get("challenge", "")),
            payload.webauthn_response,
        )
    except Exception as e:
        logger.warning("Passkey verification failed for user %s: %s", user.id, e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passkey verification failed")

    return await login_service.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        mfa_completed=True,
        method=mfa.MFA_METHOD_WEBAUTHN,
    )


@router.post(
    "/login",
    response_model=TokenWithProfile | PendingMfaResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
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


@router.post(
    "/login/json",
    response_model=TokenWithProfile | PendingMfaResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
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
    challenge_type: str | list[str] | None = None
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
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return await login_service.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        mfa_completed=True,
        method=str(challenge.challenge_type),
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
