import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

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
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_login_service,
    get_session_service,
    get_user_service,
    require_fresh_mfa,
    require_fresh_mfa_for_enrollment,
)
from app.api.validation import (
    raise_unauthorized,
)
from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.auth.security import (
    decode_token,
)
from app.core.container import get_audit_service
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.models.models import (
    ActiveSession,
    MfaTotpEnrollment,
    User,
)
from app.schemas.schemas import (
    MfaFactorStatusOut,
    MfaTotpEnrollmentOut,
    RecoveryCodesGenerateOut,
    SessionSigningKeyOut,
    TokenWithProfile,
    UserCreate,
    WebAuthnAuthenticationOptionsOut,
    WebAuthnRegistrationOptionsOut,
    WebAuthnRegistrationVerifyIn,
)
from app.services.audit_service import AuditService
from app.services.auth.login_service import LoginService
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger("app.auth")


router = APIRouter(prefix="/auth", tags=["auth"])


# Helper functions for internal logic
def _audit_log(
    action: str,
    request: Request,
    user_id: Any | None = None,
    reason: str | None = None,
    extra: dict | None = None,
) -> None:
    service = get_audit_service()
    service.log(
        event=action,
        request=request,
        user_id=user_id,
        reason=reason,
        **(extra or {}),
    )


def _extract_client_info(request: Request) -> tuple[str | None, str | None]:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return client_ip, user_agent


# Removed legacy session helpers in favor of SessionService and LoginService


async def _build_token_response(
    db: AsyncSession, user: User, token: str, session: ActiveSession
) -> TokenWithProfile:
    from app.schemas.schemas import UserProfile

    return TokenWithProfile(
        access_token=token,
        token_type="bearer",
        user=UserProfile.model_validate(user),
    )


async def _resolve_mfa_capabilities(db: AsyncSession, user: User) -> dict[str, bool]:
    # Placeholder for capabilities logic if needed locally,
    # though it should ideally be in mfa module.
    return {
        mfa.MFA_METHOD_TOTP: await mfa.has_totp_enabled(db, user),
        mfa.MFA_METHOD_WEBAUTHN: await mfa.has_webauthn_enabled(db, user),
    }


async def _collect_mfa_challenges(
    db: AsyncSession,
    user: User,
    locale: str,
    capabilities: dict[str, bool],
    session: ActiveSession | None = None,
) -> list[auth_schemas.MfaChallengeEntry]:
    methods = []
    if capabilities.get(mfa.MFA_METHOD_TOTP):
        methods.append(
            auth_schemas.MfaChallengeEntry(
                method=mfa.MFA_METHOD_TOTP,
                challenge_token=secrets.token_urlsafe(32),  # Simplified for now
            )
        )
    # Add other methods as needed
    return methods


# Legacy helper logic relocated to LoginService and LockoutService


@router.post(
    "/login/passkey/start",
    response_model=WebAuthnAuthenticationOptionsOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_passkey_start(
    payload: auth_schemas.LoginPasskeyStartIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
):
    normalized_email = payload.email.strip().lower()
    res = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = res.scalars().first()

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)

    if not user or not user.is_active:
        # Avoid user enumeration by returning dummy options
        webauthn_options = service.get_dummy_authentication_options()
        # We still issue a challenge to keep the timing consistent, but it won't
        # be valid because the user_id will be random/non-existent.
        challenge_token = secrets.token_urlsafe(48)
        # We don't save this challenge to DB to avoid filling it with junk,
        # or we could save it with a special 'dummy' user_id.
        # But for simplicity, we just return the token.
        return WebAuthnAuthenticationOptionsOut(
            publicKey=webauthn_options,
            challenge_token=challenge_token,
        )

    webauthn_options = await service.get_authentication_options(user)

    challenge = await mfa.issue_challenge(
        db,
        user_id=user.id,
        session_id=None,
        challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH,
        locale=resolve_locale(request, user=user),
        payload={"options": webauthn_options},
    )
    await db.commit()

    _audit_log(
        "auth.login.passkey_start",
        request,
        user_id=user.id,
        reason="issued",
        extra={"challenge_id": challenge.id},
    )

    return WebAuthnAuthenticationOptionsOut(
        publicKey=webauthn_options,
        challenge_token=challenge.token,
    )


@router.post(
    "/login/passkey/verify",
    response_model=TokenWithProfile | auth_schemas.PendingMfaResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_passkey_verify(
    payload: auth_schemas.LoginPasskeyVerifyIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    session_service: Any = Depends(get_session_service),
    login_service: LoginService = Depends(get_login_service),
):
    try:
        challenge = await mfa.get_challenge(
            db,
            token=payload.challenge_token,
            challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH,
            consume=True,  # ATOMIC CONSUMPTION
        )
    except HTTPException as exc:
        _audit_log(
            "auth.login.passkey_verify_failure",
            request,
            reason="challenge_lookup",
            extra={"status_code": exc.status_code},
        )
        raise

    user = await db.get(User, challenge.user_id)
    if not user or not user.is_active:
        _audit_log(
            "auth.login.passkey_verify_failure",
            request,
            user_id=challenge.user_id,
            reason="user_unavailable",
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge user unavailable")

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)
    webauthn_challenge = challenge.payload.get("options", {}).get("challenge")
    if not webauthn_challenge:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge data missing")

    try:
        await service.verify_authentication(
            user=user,
            challenge=webauthn_challenge,
            response=payload.webauthn_response,
        )
    except Exception:
        logger.error(
            "Passkey authentication failed",
            exc_info=True,
            extra={
                "user_id": str(user.id) if user else None,
                "event": "webauthn_verification_error",
            },
        )
        _audit_log(
            "auth.login.passkey_verify_failure",
            request,
            user_id=user.id,
            reason="webauthn_verification_failed",
        )
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
    response_model=TokenWithProfile | auth_schemas.PendingMfaResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": auth_schemas.PendingMfaResponse}},
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
    result = await login_service.perform_login(
        form_data.username,
        form_data.password,
        request,
        response,
        bg_tasks,
        trust_device=trust_device,
    )
    if isinstance(result, auth_schemas.PendingMfaResponse):
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post(
    "/login-json",
    response_model=TokenWithProfile | auth_schemas.PendingMfaResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": auth_schemas.PendingMfaResponse}},
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_json(
    payload: auth_schemas.LoginIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    login_service: LoginService = Depends(get_login_service),
):
    result = await login_service.perform_login(
        payload.email,
        payload.password,
        request,
        response,
        bg_tasks,
        trust_device=payload.trust_device,
    )
    if isinstance(result, auth_schemas.PendingMfaResponse):
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post(
    "/mfa/totp/start",
    response_model=auth_schemas.TotpEnrollmentStartOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def start_totp_enrollment_endpoint(
    request: Request,
    payload: auth_schemas.TotpEnrollmentStartIn | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    label = payload.label if payload else None
    reuse_existing = bool(payload.reuse_existing) if payload else False
    enrollment, secret, otpauth_url = await mfa.start_totp_enrollment(
        db,
        user=user,
        label=label,
        reuse_existing=reuse_existing,
    )
    await db.commit()
    await db.refresh(enrollment)
    _audit_log(
        "auth.mfa.totp.enroll_start",
        request,
        user_id=user.id,
        reason="issued",
        extra={"enrollment_id": enrollment.id, "label": label},
    )
    return auth_schemas.TotpEnrollmentStartOut(
        enrollment=MfaTotpEnrollmentOut.model_validate(enrollment),
        secret=secret,
        otpauth_url=otpauth_url,
    )


@router.post(
    "/mfa/totp/confirm",
    response_model=MfaTotpEnrollmentOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def confirm_totp_enrollment(
    payload: auth_schemas.TotpEnrollmentConfirmIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    enrollment = await db.get(MfaTotpEnrollment, payload.enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    try:
        updated = await mfa.complete_totp_enrollment(
            db, enrollment=enrollment, code=payload.code
        )
    except HTTPException:
        _audit_log(
            "auth.mfa.totp.enroll_failure",
            request,
            user_id=user.id,
            reason="invalid_code",
            extra={"enrollment_id": payload.enrollment_id},
        )
        raise
    await mfa.refresh_user_mfa_preferences(db, user=user)
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    await mfa.record_mfa_success(
        db,
        user=user,
        session=session,
        method=mfa.MFA_METHOD_TOTP,
    )
    await db.commit()
    await db.refresh(updated)
    _audit_log(
        "auth.mfa.totp.enroll_complete",
        request,
        user_id=user.id,
        reason="confirmed",
        extra={"enrollment_id": updated.id},
    )
    return MfaTotpEnrollmentOut.model_validate(updated)


@router.get("/mfa/totp", response_model=list[MfaTotpEnrollmentOut])
async def list_totp_enrollments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
        .order_by(MfaTotpEnrollment.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        MfaTotpEnrollmentOut.model_validate(enrollment)
        for enrollment in result.scalars()
    ]


@router.delete(
    "/mfa/totp/pending/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_pending_totp_enrollment(
    enrollment_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    enrollment = await db.get(MfaTotpEnrollment, enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    if enrollment.confirmed_at is not None or enrollment.revoked_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enrollment is not pending")

    await db.delete(enrollment)
    await db.commit()
    _audit_log(
        "auth.mfa.totp.pending_cancel",
        request,
        user_id=user.id,
        reason="pending_cancelled",
        extra={"enrollment_id": enrollment_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/mfa/totp/{enrollment_id}", response_model=MfaFactorStatusOut)
async def delete_totp_enrollment(
    enrollment_id: UUID,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    disabled_count = await mfa.disable_totp(db, user=user, enrollment_id=enrollment_id)
    await mfa.refresh_user_mfa_preferences(db, user=user)
    payload = MfaFactorStatusOut(
        disabled=bool(disabled_count),
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )
    await db.commit()
    _audit_log(
        "auth.mfa.totp.disabled",
        request,
        user_id=user.id,
        reason="revoked",
        extra={
            "disabled": bool(disabled_count),
            "enrollment_id": enrollment_id,
            "default_method": payload.mfa_default_method,
            "mfa_required": payload.mfa_required,
        },
    )
    return payload


@router.post(
    "/mfa/webauthn/register/start",
    response_model=WebAuthnRegistrationOptionsOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def start_webauthn_registration(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)
    options = await service.get_registration_options(user)

    # Store challenge in a temporary challenge record
    challenge = await mfa.issue_challenge(
        db,
        user_id=user.id,
        challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_REG,
        payload={"options": options},
    )

    await db.commit()

    _audit_log(
        "auth.mfa.webauthn.enroll_start",
        request,
        user_id=user.id,
        reason="issued",
        extra={"challenge_id": challenge.id},
    )

    return WebAuthnRegistrationOptionsOut(
        publicKey=options,
        challenge_token=challenge.token,
    )


@router.post(
    "/mfa/webauthn/register/confirm",
    response_model=MfaFactorStatusOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def confirm_webauthn_registration(
    payload: WebAuthnRegistrationVerifyIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify challenge
    challenge = await mfa.get_challenge(
        db,
        token=payload.challenge,
        challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_REG,
        user_id=user.id,
        consume=True,
    )

    webauthn_challenge = challenge.payload.get("options", {}).get("challenge")
    if not webauthn_challenge:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge data missing")

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)

    try:
        await service.verify_registration(
            user=user,
            challenge=webauthn_challenge,
            response=payload.response,
            label=payload.label,
        )
    except Exception as exc:
        logger.error(f"WebAuthn registration verification failed: {exc}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "WebAuthn verification failed")

    await mfa.refresh_user_mfa_preferences(db, user=user)
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    await mfa.record_mfa_success(
        db,
        user=user,
        session=session,
        method=mfa.MFA_METHOD_WEBAUTHN,
    )
    await db.commit()

    _audit_log(
        "auth.mfa.webauthn.enroll_complete",
        request,
        user_id=user.id,
        reason="confirmed",
    )

    return MfaFactorStatusOut(
        disabled=False,
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )


@router.get("/mfa/webauthn", response_model=list[dict[str, Any]])
async def list_webauthn_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(mfa.WebAuthnCredential)
        .where(mfa.WebAuthnCredential.user_id == user.id)
        .order_by(mfa.WebAuthnCredential.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": c.id,
            "label": c.label,
            "created_at": c.created_at,
            "last_used_at": c.last_used_at,
            "credential_id": c.credential_id,
        }
        for c in result.scalars()
    ]


@router.post(
    "/mfa/recovery-codes",
    response_model=RecoveryCodesGenerateOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def generate_recovery_codes_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    codes = await mfa.generate_recovery_codes(db, user=user)
    await db.commit()

    _audit_log(
        "auth.mfa.recovery_codes.generated",
        request,
        user_id=user.id,
        reason="user_request",
    )
    return RecoveryCodesGenerateOut(codes=codes, created_at=datetime.now(UTC))


@router.delete("/mfa/webauthn/{credential_id}", response_model=MfaFactorStatusOut)
async def delete_webauthn_credential(
    credential_id: UUID,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        delete(mfa.WebAuthnCredential)
        .where(mfa.WebAuthnCredential.id == credential_id)
        .where(mfa.WebAuthnCredential.user_id == user.id)
    )
    result = await db.execute(stmt)
    await mfa.refresh_user_mfa_preferences(db, user=user)
    await db.commit()

    payload = MfaFactorStatusOut(
        disabled=bool(result.rowcount),
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )

    _audit_log(
        "auth.mfa.webauthn.disabled",
        request,
        user_id=user.id,
        reason="revoked",
        extra={
            "disabled": bool(result.rowcount),
            "credential_id": credential_id,
            "default_method": payload.mfa_default_method,
            "mfa_required": payload.mfa_required,
        },
    )
    return payload


@router.post("/mfa/verify", response_model=TokenWithProfile)
async def verify_mfa_challenge(
    payload: auth_schemas.MfaVerifyIn,
    response: Response,
    request: Request,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    login_service: LoginService = Depends(get_login_service),
) -> TokenWithProfile:
    challenge, mfa_session = await mfa.consume_challenge(
        db,
        user_id=None,
        challenge_token=payload.challenge_token,
        provided_code=payload.code,
        provided_webauthn_response=payload.webauthn_response,
        provided_recovery_code=payload.code
        if payload.method == mfa.MFA_METHOD_RECOVERY_CODE
        else None,
        challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH
        if payload.method == mfa.MFA_METHOD_WEBAUTHN
        else mfa.CHALLENGE_TYPE_TOTP_AUTH,
        locale=resolve_locale(request=request),
    )

    user = await db.get(User, challenge.user_id)
    if not user:
        raise_unauthorized(resolve_locale(request=request))

    return await login_service.finalize_login(
        user, request, response, bg_tasks, mfa_completed=True
    )


@router.post(
    "/mfa/step-up",
    response_model=auth_schemas.PendingMfaResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": auth_schemas.PendingMfaResponse}},
)
async def request_step_up(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = getattr(request.state, "active_session", None)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Active session required")
    locale = resolve_locale(request=request, user=user)
    capabilities = await _resolve_mfa_capabilities(db, user=user)
    methods = await _collect_mfa_challenges(
        db,
        user=user,
        locale=locale,
        capabilities=capabilities,
        session=session,
    )
    if not methods:
        message = translate("errors.auth.mfa_totp_missing", locale=locale)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=message)
    await db.commit()
    payload = auth_schemas.PendingMfaResponse(
        user_id=user.id,
        session_id=session.id,
        default_method=user.mfa_default_method or mfa.MFA_METHOD_TOTP,
        methods=methods,
    )
    _audit_log(
        "auth.mfa.step_up.requested",
        request,
        user_id=user.id,
        reason="challenge_issued",
        extra={"session_id": session.id, "methods": [m.method for m in methods]},
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=payload.model_dump(mode="json"),
    )


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
    except Exception as exc:  # pragma: no cover - defensive guard
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

            from app.core.container import get_audit_service

            audit = get_audit_service()
            audit.log(
                "auth.logout.revoked",
                request,
                user_id=session.user_id,
                reason="user_initiated",
            )

    LoginService.clear_access_token_cookie(response)
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
    return {"message": "Logged out successfully"}
