from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select

from app.api.deps import (
    get_current_user,
    require_fresh_mfa,
)
from app.api.validation import raise_http_error
from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.auth.schemas import (
    TotpEnrollmentConfirmIn,
    TotpEnrollmentStartIn,
    TotpEnrollmentStartOut,
)
from app.core.fingerprint import extract_request_fingerprint
from app.core.protocols import AsyncDatabaseSession
from app.core.ratelimit import RateLimitExceeded
from app.models import User
from app.models.auth import MfaTotpEnrollment
from app.schemas.schemas import (
    MfaFactorStatusOut,
    MfaTotpEnrollmentOut,
    RecoveryCodesGenerateOut,
)
from app.services.audit_service import AuditService
from app.services.auth.login_service import LoginService

if TYPE_CHECKING:
    from app.models import ActiveSession

logger = logging.getLogger("app.auth.mfa")

router = APIRouter(tags=["mfa"])


async def _commit_and_publish_mfa_revocations(
    db: AsyncDatabaseSession,
    pending: list[mfa.MfaSessionRevocation],
) -> None:
    try:
        await db.commit()
    except Exception:  # RZ-22-01-JUSTIFIED: transaction cleanup before re-raise
        await db.rollback()
        raise
    await mfa.publish_mfa_session_revocations(pending)


def _mfa_rate_limit_error(exc: RateLimitExceeded) -> HTTPException:
    retry_after = max(0, int(exc.info.retry_after))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "MFA request rejected",
        headers={"Retry-After": str(retry_after)},
    )


async def _issue_email_challenge_for_session(
    *,
    flow: str,
    request: Request,
    db: AsyncDatabaseSession,
    login_service: LoginService,
    user: User,
) -> auth_schemas.MfaMethodChallengeOut:
    from app.auth.mfa.email_otp import MfaOtpRejected, MfaSecurityUnavailable
    from app.core.localization import resolve_locale
    from app.core.ratelimit import resolve_client_ip

    session = getattr(request.state, "active_session", None)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA request rejected")
    try:
        issued = await login_service.get_email_otp_service().issue(
            db,
            user_id=user.id,
            flow=flow,
            session_identifier=str(session.id),
            client_fingerprint=extract_request_fingerprint(request),
            client_ip=resolve_client_ip(request) or "unknown",
            locale=resolve_locale(request=request, user=user),
        )
        await db.commit()
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc) from exc
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
    return auth_schemas.MfaMethodChallengeOut(
        method=mfa.MFA_METHOD_EMAIL_OTP,
        challenge_token=issued.challenge_token,
        challenge_expires_at=issued.expires_at,
        attempt_count=0,
        attempt_limit=5,
        remaining_attempts=5,
        delivery_hint=issued.delivery_hint,
        resend_available_at=issued.resend_available_at,
        revision=issued.revision,
    )


@router.post(
    "/mfa/email/verification/start",
    response_model=auth_schemas.MfaMethodChallengeOut,
)
@inject
async def start_email_verification(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    login_service: FromDishka[LoginService],
    user: User = Depends(get_current_user),
) -> auth_schemas.MfaMethodChallengeOut:
    return await _issue_email_challenge_for_session(
        flow="email_verification",
        request=request,
        db=db,
        login_service=login_service,
        user=user,
    )


@router.post(
    "/mfa/email/enable",
    response_model=auth_schemas.MfaMethodChallengeOut,
    dependencies=[Depends(require_fresh_mfa)],
)
@inject
async def start_email_mfa_enablement(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    login_service: FromDishka[LoginService],
    user: User = Depends(get_current_user),
) -> auth_schemas.MfaMethodChallengeOut:
    return await _issue_email_challenge_for_session(
        flow="email_mfa_enablement",
        request=request,
        db=db,
        login_service=login_service,
        user=user,
    )


@router.delete(
    "/mfa/email",
    response_model=MfaFactorStatusOut,
    dependencies=[Depends(require_fresh_mfa)],
)
@inject
async def disable_email_mfa_endpoint(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    user: User = Depends(get_current_user),
) -> MfaFactorStatusOut:
    pending = await mfa.disable_email_mfa(db, user=user)
    await _commit_and_publish_mfa_revocations(db, pending)
    audit.log("auth.mfa.email.disabled", request, user_id=user.id, reason="revoked")
    return MfaFactorStatusOut(
        disabled=True,
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )


@router.post(
    "/mfa/totp/start",
    response_model=TotpEnrollmentStartOut,
    dependencies=[Depends(require_fresh_mfa)],
)
@inject
async def start_totp_enrollment_endpoint(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    payload: TotpEnrollmentStartIn | None = None,
    user: User = Depends(get_current_user),
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
    dependencies=[Depends(require_fresh_mfa)],
)
@inject
async def confirm_totp_enrollment(
    payload: TotpEnrollmentConfirmIn,
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    user: User = Depends(get_current_user),
) -> MfaTotpEnrollmentOut:
    # complete_totp_enrollment owns the User -> enrollment lock order.
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
    if session is None:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA verification failed")
    try:
        pending_revocations = await mfa.revoke_sibling_sessions_for_factor_change(
            db,
            user_id=user.id,
            current_session_id=session.id,
        )
        await mfa.record_mfa_success(
            db,
            user=user,
            session=session,
            method=mfa.MFA_METHOD_TOTP,
        )
        await db.commit()
    except (
        Exception
    ):  # RZ-22-01-JUSTIFIED: transaction boundary rolls back then re-raises
        await db.rollback()
        raise
    await mfa.publish_mfa_session_revocations(pending_revocations)
    await db.refresh(updated)

    audit.log(
        "auth.mfa.totp.enroll_complete",
        request,
        user_id=user.id,
        reason="confirmed",
        extra={"enrollment_id": updated.id},
    )

    # RZ-07 (audit 2026-03-15 Wave 7): CSRF rotation on MFA enrollment completion.
    # Adding a second factor is a privilege escalation — rotate the CSRF token so
    # any pre-enrollment CSRF cookies captured by an attacker become invalid.
    from app.core.csrf import signal_csrf_rotation

    signal_csrf_rotation(request)

    return MfaTotpEnrollmentOut.model_validate(updated)


@router.get("/mfa/totp", response_model=list[MfaTotpEnrollmentOut])
@inject
async def list_totp_enrollments(
    user: User = Depends(get_current_user),
    db: FromDishka[AsyncDatabaseSession] = Depends(),
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
@inject
async def delete_pending_totp_enrollment(
    enrollment_id: UUID,
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    user: User = Depends(get_current_user),
) -> None:
    enrollment = await db.get(MfaTotpEnrollment, enrollment_id, with_for_update=True)
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


@router.delete("/mfa/totp/{enrollment_id}", response_model=MfaFactorStatusOut)
@inject
async def delete_totp_enrollment(
    enrollment_id: UUID,
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
) -> MfaFactorStatusOut:
    disabled_count, pending = await mfa.disable_totp(
        db, user=user, enrollment_id=enrollment_id
    )
    await mfa.refresh_user_mfa_preferences(db, user=user)
    payload = MfaFactorStatusOut(
        disabled=bool(disabled_count),
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )
    await _commit_and_publish_mfa_revocations(db, pending)

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


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesGenerateOut)
@inject
async def generate_recovery_codes_endpoint(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
) -> RecoveryCodesGenerateOut:
    session: ActiveSession | None = getattr(request.state, "active_session", None)
    codes = await mfa.generate_recovery_codes(
        db,
        user=user,
        fresh_mfa_verified_at=session.mfa_verified_at if session else None,
    )
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
@inject
async def request_step_up(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    audit: FromDishka[AuditService],
    login_service: FromDishka[LoginService],
    user: User = Depends(get_current_user),
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

    try:
        methods = await login_service._collect_mfa_challenges(
            user,
            locale,
            capabilities,
            session,
            request=request,
            flow="step_up",
        )
    except RateLimitExceeded as exc:
        await db.rollback()
        raise _mfa_rate_limit_error(exc) from exc
    preferred = str(user.mfa_default_method or "")
    default_method = (
        preferred
        if preferred in {mfa.MFA_METHOD_TOTP, mfa.MFA_METHOD_EMAIL_OTP}
        and capabilities.get(preferred, False)
        else (
            mfa.MFA_METHOD_TOTP
            if capabilities.get(mfa.MFA_METHOD_TOTP, False)
            else mfa.MFA_METHOD_EMAIL_OTP
        )
    )
    await db.commit()

    audit.log(
        "auth.mfa.step_up_requested",
        request,
        user_id=user.id,
    )

    pending = auth_schemas.PendingMfaResponse(
        user_id=user.id,
        session_id=session.id if session else None,
        default_method=cast(
            "Literal['totp', 'email_otp'] | None",
            default_method,
        ),
        methods=methods,
    )
    return pending
