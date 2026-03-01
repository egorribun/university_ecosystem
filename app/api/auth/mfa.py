from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select

from app.api.deps import (
    get_audit_service,
    get_current_user,
    get_db,
    get_login_service,
    require_fresh_mfa,
    require_fresh_mfa_for_enrollment,
)
from app.api.validation import raise_http_error
from app.auth import constants, mfa
from app.auth import schemas as auth_schemas
from app.auth.schemas import (
    TotpEnrollmentConfirmIn,
    TotpEnrollmentStartIn,
    TotpEnrollmentStartOut,
)
from app.models.auth import MfaTotpEnrollment
from app.schemas.schemas import (
    MfaFactorStatusOut,
    MfaTotpEnrollmentOut,
    RecoveryCodesGenerateOut,
    WebAuthnRegistrationOptionsOut,
    WebAuthnRegistrationVerifyIn,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import ActiveSession, User
    from app.services.audit_service import AuditService
    from app.services.auth.login_service import LoginService

logger = logging.getLogger("app.auth.mfa")

router = APIRouter(tags=["mfa"])


@router.post(
    "/mfa/totp/start",
    response_model=TotpEnrollmentStartOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def start_totp_enrollment_endpoint(
    request: Request,
    payload: TotpEnrollmentStartIn | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> TotpEnrollmentStartOut:
    label = payload.label if payload else None
    reuse_existing = bool(payload.reuse_existing) if payload else False

    user_id = user.id
    from app.models.user_loaders import ensure_mfa_relationships_loaded

    await ensure_mfa_relationships_loaded(db, user)

    enrollment, secret, otpauth_url = await mfa.start_totp_enrollment(
        db,
        user=user,
        label=label,
        reuse_existing=reuse_existing,
    )
    await db.commit()
    await db.refresh(enrollment)

    audit.log(
        "auth.mfa.totp.enroll_start",
        request,
        user_id=user_id,
        reason="issued",
        extra={"enrollment_id": enrollment.id, "label": label},
    )

    return TotpEnrollmentStartOut(
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
    payload: TotpEnrollmentConfirmIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> MfaTotpEnrollmentOut:
    enrollment = await db.get(MfaTotpEnrollment, payload.enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")

    try:
        updated = await mfa.complete_totp_enrollment(
            db, enrollment=enrollment, code=payload.code
        )
    except HTTPException:
        audit.log(
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

    audit.log(
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
) -> list[MfaTotpEnrollmentOut]:
    stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
        .order_by(MfaTotpEnrollment.created_at.desc())
    )
    result = await db.execute(stmt)
    return [MfaTotpEnrollmentOut.model_validate(e) for e in result.scalars()]


@router.delete(
    "/mfa/totp/pending/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_pending_totp_enrollment(
    enrollment_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    enrollment = await db.get(MfaTotpEnrollment, enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    if enrollment.confirmed_at is not None or enrollment.revoked_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enrollment is not pending")

    await db.delete(enrollment)
    await db.commit()

    audit.log(
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
    audit: AuditService = Depends(get_audit_service),
) -> MfaFactorStatusOut:
    disabled_count = await mfa.disable_totp(db, user=user, enrollment_id=enrollment_id)
    await mfa.refresh_user_mfa_preferences(db, user=user)
    payload = MfaFactorStatusOut(
        disabled=bool(disabled_count),
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )
    await db.commit()

    audit.log(
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
    audit: AuditService = Depends(get_audit_service),
) -> WebAuthnRegistrationOptionsOut:
    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)
    options = await service.get_registration_options(user)

    challenge = await mfa.issue_challenge(
        db,
        user_id=user.id,
        challenge_type=constants.CHALLENGE_TYPE_WEBAUTHN_REG,
        payload={"options": options},
    )
    await db.commit()

    audit.log(
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
    audit: AuditService = Depends(get_audit_service),
) -> MfaFactorStatusOut:
    challenge = await mfa.get_challenge(
        db,
        token=payload.challenge,
        challenge_type=constants.CHALLENGE_TYPE_WEBAUTHN_REG,
        consume=True,
    )

    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db)

    try:
        payload_dict: dict[str, Any] = challenge.payload  # type: ignore[assignment]
        await service.verify_registration(
            user,
            str(payload_dict.get("options", {}).get("challenge", "")),
            payload.response,
            label=payload.label,
        )
    except Exception as e:
        logger.warning(
            f"Passkey registration verification failed for user {user.id}: {e}"
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Passkey verification failed"
        ) from e

    await mfa.refresh_user_mfa_preferences(db, user=user)
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    await mfa.record_mfa_success(
        db,
        user=user,
        session=session,
        method=mfa.MFA_METHOD_WEBAUTHN,
    )
    await db.commit()

    audit.log(
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
) -> list[dict[str, Any]]:
    from app.models.models import WebAuthnCredential

    stmt = select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    result = await db.execute(stmt)
    return [
        {
            "id": c.id,
            "label": c.label,
            "created_at": c.created_at,
            "last_used_at": c.last_used_at,
        }
        for c in result.scalars()
    ]


@router.delete("/mfa/webauthn/{credential_id}", response_model=MfaFactorStatusOut)
async def delete_webauthn_credential(
    credential_id: UUID,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> MfaFactorStatusOut:
    from app.models.models import WebAuthnCredential

    cred = await db.get(WebAuthnCredential, credential_id)
    if not cred or cred.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")

    await db.delete(cred)
    await mfa.refresh_user_mfa_preferences(db, user=user)
    await db.commit()

    audit.log(
        "auth.mfa.webauthn.revoked",
        request,
        user_id=user.id,
        reason="revoked",
        extra={"credential_id": credential_id},
    )

    return MfaFactorStatusOut(
        disabled=True,
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesGenerateOut)
async def generate_recovery_codes_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> RecoveryCodesGenerateOut:
    codes = await mfa.generate_recovery_codes(db, user=user)
    await db.commit()

    audit.log(
        "auth.mfa.recovery_codes.generated",
        request,
        user_id=user.id,
        reason="user_requested",
    )

    from datetime import UTC, datetime

    return RecoveryCodesGenerateOut(
        codes=codes,
        created_at=datetime.now(UTC),
    )


@router.post(
    "/mfa/step-up",
    response_model=auth_schemas.PendingMfaResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_step_up(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    login_service: LoginService = Depends(get_login_service),
) -> auth_schemas.PendingMfaResponse:
    from app.core.localization import resolve_locale

    locale = resolve_locale(request=request, user=user)
    session: ActiveSession | None = getattr(request.state, "active_session", None)

    capabilities = await login_service._resolve_mfa_capabilities(user)

    from app.models.user_loaders import ensure_mfa_relationships_loaded

    await ensure_mfa_relationships_loaded(db, user)

    if not mfa.user_has_confirmed_interactive_factor(user):
        raise_http_error(
            status.HTTP_400_BAD_REQUEST,
            "errors.auth.mfa_totp_missing",
            locale,
        )

    methods = await login_service._collect_mfa_challenges(
        user, locale, capabilities, session
    )
    await db.commit()

    audit.log(
        "auth.mfa.step_up_requested",
        request,
        user_id=user.id,
    )

    return auth_schemas.PendingMfaResponse(
        user_id=user.id,
        session_id=session.id if session else None,
        default_method=user.mfa_default_method or mfa.MFA_METHOD_TOTP,
        methods=methods,
    )
