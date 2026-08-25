from __future__ import annotations

import logging
from typing import Any

from dishka.integrations.fastapi import FromDishka, inject
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

from app.api.deps import (
    get_current_user,
)
from app.auth import constants, mfa
from app.auth.handlers.logout import router as logout_router
from app.auth.mfa.email_otp import (
    MfaNotEmailChallenge,
    MfaOtpCooldown,
    MfaOtpRejected,
    MfaSecurityUnavailable,
)
from app.auth.schemas import (
    EmailOtpResendIn,
    LoginIn,
    MfaMethodChallengeOut,
    MfaVerifyIn,
    PendingMfaResponse,
)
from app.core.config import settings
from app.core.fingerprint import extract_request_fingerprint
from app.core.localization import resolve_locale, translate
from app.core.protocols import AsyncDatabaseSession
from app.core.ratelimit import RateLimitExceeded, sensitive_route_limit
from app.models import User
from app.schemas.schemas import (
    SessionSigningKeyOut,
    TokenWithProfile,
    UserCreate,
)
from app.services.auth.login_service import LoginService
from app.services.auth.mfa_coordinator import MfaCoordinator
from app.services.user.compliance_service import UserComplianceService

logger = logging.getLogger("app.auth.login")


router = APIRouter(tags=["auth"])
router.include_router(logout_router)


def _mfa_rate_limit_error(exc: RateLimitExceeded, *, detail: str) -> HTTPException:
    retry_after = max(0, int(exc.info.retry_after))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail,
        headers={"Retry-After": str(retry_after)},
    )


@router.post(
    "/login",
    response_model=TokenWithProfile | PendingMfaResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(sensitive_route_limit())],
)
@inject
async def login(
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    login_service: FromDishka[LoginService],
    db: FromDishka[AsyncDatabaseSession],
    trust_device: bool = Form(False),
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
) -> TokenWithProfile | PendingMfaResponse:
    try:
        result = await login_service.perform_login(
            email=form_data.username,
            password=form_data.password,
            request=request,
            response=response,
            bg_tasks=bg_tasks,
            trust_device=trust_device,
        )
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc, detail="MFA request rejected") from exc
    except MfaSecurityUnavailable as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "MFA service unavailable"
        ) from exc
    if isinstance(result, PendingMfaResponse):
        await db.commit()
    return result


@router.post(
    "/login/json",
    response_model=TokenWithProfile | PendingMfaResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(sensitive_route_limit())],
)
@inject
async def login_json(
    payload: LoginIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    login_service: FromDishka[LoginService],
    db: FromDishka[AsyncDatabaseSession],
) -> TokenWithProfile | PendingMfaResponse:
    try:
        result = await login_service.perform_login(
            email=payload.email,
            password=payload.password,
            request=request,
            response=response,
            bg_tasks=bg_tasks,
            trust_device=payload.trust_device,
        )
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc, detail="MFA request rejected") from exc
    except MfaSecurityUnavailable as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "MFA service unavailable"
        ) from exc
    if isinstance(result, PendingMfaResponse):
        await db.commit()
    return result


@router.post(
    "/mfa/verify",
    response_model=TokenWithProfile,
    response_model_exclude_none=True,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_auth_mfa))
    ],
)
@inject
async def verify_mfa_challenge(
    payload: MfaVerifyIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    login_service: FromDishka[LoginService],
    db: FromDishka[AsyncDatabaseSession],
) -> TokenWithProfile:
    active_session = getattr(request.state, "active_session", None)
    active_session_identifier = (
        str(active_session.id) if active_session is not None else None
    )
    login_session_identifier = request.cookies.get(MfaCoordinator.PREAUTH_COOKIE_NAME)
    client_fingerprint = extract_request_fingerprint(request)
    from app.core.ratelimit import resolve_client_ip

    client_ip = resolve_client_ip(request) or "unknown"

    challenge_type: str | list[str] = constants.CHALLENGE_TYPE_TOTP_VERIFY
    if payload.method == constants.MFA_METHOD_TOTP:
        challenge_type = constants.CHALLENGE_TYPE_TOTP_VERIFY
    elif payload.method == constants.MFA_METHOD_RECOVERY_CODE:
        # Recovery code can be used for any auth challenge
        challenge_type = [
            constants.CHALLENGE_TYPE_TOTP_VERIFY,
        ]
    elif payload.method != constants.MFA_METHOD_EMAIL_OTP:
        # Invalid method
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA method"
        )

    try:
        if payload.method == constants.MFA_METHOD_EMAIL_OTP:
            if not payload.code:
                raise MfaOtpRejected()
            email_otp_service = login_service.get_email_otp_service()
            challenge = await email_otp_service.verify_opaque(
                db,
                challenge_token=payload.challenge_token,
                code=payload.code,
                client_fingerprint=client_fingerprint,
                client_ip=client_ip,
                login_session_identifier=login_session_identifier,
                active_session_identifier=active_session_identifier,
            )
        elif payload.method == constants.MFA_METHOD_RECOVERY_CODE:
            if not payload.code:
                raise MfaOtpRejected()
            try:
                challenge = (
                    await login_service.get_email_otp_service().consume_recovery_opaque(
                        db,
                        challenge_token=payload.challenge_token,
                        code=payload.code,
                        client_fingerprint=client_fingerprint,
                        client_ip=client_ip,
                        login_session_identifier=login_session_identifier,
                        active_session_identifier=active_session_identifier,
                    )
                )
            except MfaNotEmailChallenge:
                challenge, _ = await mfa.consume_challenge(
                    db,
                    challenge_token=payload.challenge_token,
                    challenge_type=challenge_type,
                    provided_code=payload.code,
                    provided_method=payload.method,
                    client_fingerprint=client_fingerprint,
                    login_session_identifier=login_session_identifier,
                    active_session_identifier=active_session_identifier,
                )
        else:
            challenge, _ = await mfa.consume_challenge(
                db,
                challenge_token=payload.challenge_token,
                challenge_type=challenge_type,
                provided_code=payload.code,
                provided_method=payload.method,
                client_fingerprint=client_fingerprint,
                login_session_identifier=login_session_identifier,
                active_session_identifier=active_session_identifier,
            )
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc, detail="MFA verification failed") from exc
    except MfaSecurityUnavailable as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "MFA service unavailable"
        ) from exc
    except HTTPException as exc:
        # Failed-attempt CAS mutations must survive FastAPI's exception rollback.
        await db.commit()
        if exc.status_code in {
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        }:
            raise
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA verification failed"
        ) from exc
    except MfaOtpRejected as exc:
        await db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA verification failed"
        ) from exc

    user = await db.get(User, challenge.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA verification failed")

    if challenge.trust_device_requested:
        try:
            token, expires_at = await mfa.create_trusted_device_token(
                db,
                user=user,
                user_agent=request.headers.get("user-agent") or "unknown",
                ip_address=client_ip,
            )
        except (RuntimeError, MfaSecurityUnavailable) as exc:
            await db.rollback()
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "MFA service unavailable"
            ) from exc
        response.set_cookie(
            settings.trusted_device_cookie_name,
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,  # type: ignore[arg-type]
            expires=expires_at,
            max_age=settings.trusted_device_expire_days * 86400,
            path="/",
        )

    if challenge.flow in {
        "step_up",
        "email_verification",
        "email_mfa_enablement",
    }:
        if active_session is None:
            await db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA verification failed")
        result = await login_service.complete_step_up(
            user=user,
            session=active_session,
            request=request,
            method=payload.method,
        )
        await db.commit()
        await login_service.publish_completed_step_up(
            user=user,
            session=active_session,
            request=request,
        )
        return result

    result = await login_service.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        mfa_completed=True,
        method=payload.method,
    )
    response.delete_cookie(
        MfaCoordinator.PREAUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )
    return result


@router.post(
    "/mfa/email/resend",
    response_model=MfaMethodChallengeOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_auth_mfa))
    ],
)
@inject
async def resend_email_mfa_challenge(
    payload: EmailOtpResendIn,
    request: Request,
    login_service: FromDishka[LoginService],
    db: FromDishka[AsyncDatabaseSession],
) -> MfaMethodChallengeOut:
    from app.core.ratelimit import resolve_client_ip

    active_session = getattr(request.state, "active_session", None)
    try:
        issued = await login_service.get_email_otp_service().resend_opaque(
            db,
            challenge_token=payload.challenge_token,
            client_fingerprint=extract_request_fingerprint(request),
            client_ip=resolve_client_ip(request) or "unknown",
            locale=resolve_locale(request=request),
            login_session_identifier=request.cookies.get(
                MfaCoordinator.PREAUTH_COOKIE_NAME
            ),
            active_session_identifier=(
                str(active_session.id) if active_session is not None else None
            ),
        )
        await db.commit()
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc, detail="MFA request rejected") from exc
    except MfaOtpCooldown as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "MFA request rejected"
        ) from exc
    except MfaSecurityUnavailable as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "MFA service unavailable"
        ) from exc
    except MfaOtpRejected as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA request rejected"
        ) from exc
    return MfaMethodChallengeOut(
        method=constants.MFA_METHOD_EMAIL_OTP,
        challenge_token=issued.challenge_token,
        challenge_expires_at=issued.expires_at,
        attempt_count=0,
        attempt_limit=5,
        remaining_attempts=5,
        resend_available_at=issued.resend_available_at,
        revision=issued.revision,
        delivery_hint=issued.delivery_hint,
    )


@router.get(
    "/csrf-cookie",
    summary="Initialize CSRF token",
    description="This endpoint sets a new robust CSRF cookie and is intended for SPAs to call before attempting a login.",
)
async def get_csrf_cookie() -> dict[str, str]:
    return {"detail": "CSRF cookie set"}


@router.post(
    "/register",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_auth_register))
    ],
)
@inject
async def register(
    user: UserCreate,
    request: Request,
    compliance_service: FromDishka[UserComplianceService],
    login_service: FromDishka[LoginService],
    db: FromDishka[AsyncDatabaseSession],
) -> dict[str, Any]:
    locale = resolve_locale(request=request)
    try:
        new_user = await compliance_service.register_user(user)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain — converts registration errors to HTTP 400 (reviewed TD-27-04)
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
) -> SessionSigningKeyOut:
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
