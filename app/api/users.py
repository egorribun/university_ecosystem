from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response

import app.models as models
from app.api import deps
from app.api.deps import (
    get_current_admin_user,
    get_current_user,
    get_current_user_full,
    require_fresh_mfa,
)
from app.api.validation import raise_validation_error, require_admin
from app.core.config import settings
from app.core.container import (
    get_audit_service,
    get_auth_service,
    get_group_service,
    get_user_compliance_service,
    get_user_media_service,
    get_user_profile_service,
)
from app.core.database import get_read_db
from app.core.localization import resolve_locale
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.core.ratelimit import sensitive_route_limit
from app.models.enums import UserRole
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.data_access import (
    batch_log_data_access,
    log_data_access,
)
from app.services.file_scanner import scan_for_malware
from app.services.group_service import GroupService
from app.services.notifications import create_notifications_for_users
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService

# Export for test compatibility
__all__ = ["create_notifications_for_users"]

logger = get_logger(__name__)

router = APIRouter()
password_router = APIRouter(prefix="/password", tags=["password"])
users_router = APIRouter(prefix="/users", tags=["users"])
groups_router = APIRouter(prefix="/groups", tags=["groups"])

PROFILE_CACHE_HEADER = "x-profile-cache-envelope"


def _enforce_profile_cache_integrity(request: Request) -> None:
    raw_envelope = request.headers.get(PROFILE_CACHE_HEADER)
    if not raw_envelope:
        if settings.environment in ("testing", "development"):
            return
        locale = resolve_locale(request=request)
        raise_validation_error("errors.profile_cache.missing_envelope", locale)

    locale = resolve_locale(request=request)
    session = getattr(request.state, "active_session", None)

    # RZ-08 (audit 2026-03-04): Extract and validate signing_key before use.
    # The original code used str(getattr(session, "signing_key", "")) inside
    # hmac.new(), which silently coerces None→"None" or empty string→"" — both
    # produce a trivially guessable HMAC key. Guard here explicitly so mypy and
    # runtime both agree the key is a non-empty str before it reaches the HMAC call.
    signing_key: str | None = getattr(session, "signing_key", None) if session else None
    if not signing_key:
        raise_validation_error("errors.sessions.signing_key_missing", locale)

    # AUDIT-BE-04: bound header size before parsing to prevent memory amplification.
    # json.loads on a 10 MB header allocates ~30 MB (Python JSON ~3x overhead) and
    # then runs HMAC over the whole payload — DoS at 50 concurrent requests.
    # 8 KiB is more than enough for any valid profile cache envelope.
    _MAX_ENVELOPE_BYTES = 8_192
    raw_bytes = raw_envelope.encode("utf-8")
    if len(raw_bytes) > _MAX_ENVELOPE_BYTES:
        raise_validation_error("errors.profile_cache.invalid_envelope", locale)

    try:
        candidate = json.loads(raw_bytes)
    except json.JSONDecodeError:
        raise_validation_error("errors.profile_cache.invalid_envelope", locale)

    if not isinstance(candidate, dict):
        raise_validation_error("errors.profile_cache.invalid_envelope", locale)

    signature = candidate.get("signature")
    if not isinstance(signature, str) or not signature:
        raise_validation_error("errors.profile_cache.invalid_signature", locale)

    payload = {
        "version": candidate.get("version"),
        "expiresAt": candidate.get("expiresAt"),
        "data": candidate.get("data"),
    }

    if (
        payload["version"] is None
        or payload["expiresAt"] is None
        or payload["data"] is None
    ):
        raise_validation_error("errors.profile_cache.invalid_envelope", locale)

    payload_json = json.dumps(payload, separators=(",", ":"))
    digest = hmac.new(
        signing_key.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(digest).decode("ascii")

    if not hmac.compare_digest(signature, expected_signature):
        raise_validation_error("errors.profile_cache.invalid_signature", locale)

    # SEC-BE-02 (audit Wave 10): validate temporal bounds AFTER HMAC so we do
    # not leak timing information before signature verification.
    # Without this check, any previously-valid HMAC envelope can be replayed
    # indefinitely — HMAC proves authenticity, not freshness.
    try:
        val = payload["expiresAt"]
        if isinstance(val, (int, float)):
            expires_at = datetime.fromtimestamp(val / 1000.0, UTC)
        else:
            expires_at = datetime.fromisoformat(str(val))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

        if datetime.now(UTC) > expires_at:
            raise_validation_error("errors.profile_cache.envelope_expired", locale)
    except ValueError, TypeError, OSError:
        raise_validation_error("errors.profile_cache.invalid_expires_at", locale)


@password_router.post(
    "/forgot",
    dependencies=[Depends(sensitive_route_limit())],
)
async def forgot_password(
    payload: schemas.ForgotPasswordIn,
    request: Request,
    bg: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    await auth_service.initiate_password_reset(payload.email, request, bg)
    return {"ok": True}


@password_router.post(
    "/reset",
    dependencies=[Depends(sensitive_route_limit())],
)
async def reset_password(
    payload: schemas.ResetPasswordIn,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    await auth_service.perform_password_reset(payload.token, payload.password, request)
    return {"ok": True}


@users_router.get("/me", response_model=schemas.UserOut, summary="Me")
async def me(
    request: Request,
    db: AsyncDatabaseSession = Depends(get_read_db),
    user: models.User = Depends(get_current_user_full),
    auth_service: AuthService = Depends(get_auth_service),
) -> schemas.UserOut:
    _enforce_profile_cache_integrity(request)
    await auth_service.refresh_pending_email(user)
    await log_data_access(
        db,
        actor_user_id=user.id,
        subject_user_id=user.id,
        resource_type="profile",
        resource_id=str(user.id),
        action="read",
        request=request,
    )
    return schemas.UserOut.model_validate(user)


@users_router.put(
    "/me",
    response_model=schemas.UserOut,
    summary="Update Me",
    dependencies=[Depends(sensitive_route_limit())],
)
async def update_me(
    data: schemas.UserProfileUpdate,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserProfileService = Depends(get_user_profile_service),
) -> schemas.UserOut:
    user_dto = await service.update_user_profile(user, data, request)
    return schemas.UserOut.model_validate(user_dto)


@users_router.post(
    "/me/email",
    response_model=schemas.UserOut,
    dependencies=[Depends(sensitive_route_limit())],
    summary="Change Email",
)
async def change_email(
    payload: schemas.UserEmailChangeIn,
    request: Request,
    bg: BackgroundTasks,
    _: None = Depends(require_fresh_mfa),
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    auth_service: AuthService = Depends(get_auth_service),
) -> schemas.UserOut:
    user_dto = await auth_service.initiate_email_change(user, payload, request, bg)
    return schemas.UserOut.model_validate(user_dto)


@users_router.post(
    "/me/email/confirm",
    response_model=schemas.UserOut,
    dependencies=[Depends(sensitive_route_limit())],
    summary="Confirm Email Change",
)
async def verify_email_change(
    payload: schemas.UserEmailConfirmIn,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    auth_service: AuthService = Depends(get_auth_service),
) -> schemas.UserOut:
    user_dto = await auth_service.confirm_email_change(user, payload.token, request)
    return schemas.UserOut.model_validate(user_dto)


@users_router.post(
    "/me/password",
    response_model=schemas.PasswordChangeOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def change_password(
    payload: schemas.UserPasswordChangeIn,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    auth_service: AuthService = Depends(get_auth_service),
) -> schemas.PasswordChangeOut:
    ok, revoked = await auth_service.change_password(user, payload, request)
    return schemas.PasswordChangeOut(ok=ok, revoked_sessions=revoked)


@users_router.post(
    "/me/export",
    response_model=schemas.DataExportOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def export_current_user_data(
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserComplianceService = Depends(get_user_compliance_service),
) -> schemas.DataExportOut:
    return await service.export_user_data(user, request)


@users_router.post(
    "/me/delete",
    response_model=schemas.DataDeletionOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def delete_current_user_account(
    payload: schemas.DataDeletionRequest,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserComplianceService = Depends(get_user_compliance_service),
) -> schemas.DataDeletionOut:
    return await service.delete_user_data(user, request, confirm=payload.confirm)


@users_router.post(
    "/me/avatar",
    response_model=schemas.UserOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_users_avatar))
    ],
)
async def upload_avatar(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
) -> schemas.UserOut:
    await scan_for_malware(file, locale=None, size_bytes=file.size)
    user_dto = await service.upload_avatar(user, file)
    return schemas.UserOut.model_validate(user_dto)


@users_router.post(
    "/me/cover",
    response_model=schemas.UserOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_users_avatar))
    ],
)
async def upload_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
) -> schemas.UserOut:
    await scan_for_malware(file, locale=None, size_bytes=file.size)
    user_dto = await service.upload_cover(user, file)
    return schemas.UserOut.model_validate(user_dto)


@users_router.delete(
    "/me/avatar",
    response_model=schemas.UserOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_users_avatar))
    ],
)
async def delete_avatar(
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
) -> schemas.UserOut:
    user_dto = await service.delete_avatar(user)
    return schemas.UserOut.model_validate(user_dto)


@users_router.delete(
    "/me/cover",
    response_model=schemas.UserOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_users_avatar))
    ],
)
async def delete_cover(
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
) -> schemas.UserOut:
    user_dto = await service.delete_cover(user)
    return schemas.UserOut.model_validate(user_dto)


@users_router.post("", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserComplianceService = Depends(get_user_compliance_service),
) -> schemas.UserOut:
    user_dto = await service.create_user(data, request, user)
    return schemas.UserOut.model_validate(user_dto)


@users_router.get(
    "",
    response_model=list[schemas.UserPublicOut | schemas.UserOut],
    summary="Search Users",
)
async def get_users(
    request: Request,
    bg: BackgroundTasks,
    filters: schemas.UserSearchFilter = Depends(),
    current_user: UserDTO = Depends(deps.get_current_user_dto),
    service: UserProfileService = Depends(get_user_profile_service),
    db: AsyncDatabaseSession = Depends(get_read_db),
) -> list[schemas.UserPublicOut | schemas.UserOut]:
    """
    Search for users.
    Admins see full profiles (UserOut), others see only public info (UserPublicOut).
    """
    users = await service.get_users(
        request,
        current_user,
        filters=filters,
    )

    # Log data access for each fetched user
    log_entries = [
        {
            "actor_user_id": current_user.id,
            "subject_user_id": item.id,
            "resource_type": "profile",
            "resource_id": str(item.id),
            "action": "read",
        }
        for item in users
    ]
    bg.add_task(batch_log_data_access, db, entries=log_entries, request=request)

    if current_user.role != UserRole.ADMIN:
        # Force strict serialization to public schema for non-admins
        return [
            schemas.UserPublicOut.model_validate(u, from_attributes=True) for u in users
        ]

    # Admins get full objects
    return [schemas.UserOut.model_validate(u) for u in users]


@users_router.get(
    "/audit/export",
    # RZ-03 (audit 2026-03-04): Rate-limit this endpoint — it triggers a
    # potentially large DB query and CPU-intensive CSV serialization per call.
    # A compromised admin token could otherwise hammer this indefinitely.
    dependencies=[Depends(sensitive_route_limit())],
)
async def export_access_audit(
    request: Request,
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    db: AsyncDatabaseSession = Depends(get_read_db),
    user: models.User = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    from datetime import timedelta

    from fastapi import HTTPException

    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    # RZ-03: Enforce max date range to prevent full-table sequential scans.
    # A query spanning years would lock the DB reader replica under heavy load.
    if start_at and end_at and (end_at - start_at) > timedelta(days=31):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "date_range_too_large",
                "message": "Date range must not exceed 31 days",
            },
        )

    from fastapi.responses import StreamingResponse

    from app.services.data_access import export_access_logs_stream

    audit.log("users.audit.export", request, user_id=user.id)

    return StreamingResponse(
        export_access_logs_stream(
            db,
            start_at=start_at,
            end_at=end_at,
            actor_user_id=None,
            subject_user_id=None,
        ),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=access_audit.csv"},
    )


@users_router.patch("/{user_id}", response_model=schemas.UserOut)
async def update_user_admin(
    user_id: UUID,
    data: schemas.UserAdminUpdate,
    request: Request,
    # TD-6: use the SpiceDB-backed fail-closed dep at the route level so that
    # authorization is enforced in two layers (route + service).
    user: models.User = Depends(get_current_admin_user),
    service: UserProfileService = Depends(get_user_profile_service),
) -> schemas.UserOut:
    user_dto = await service.admin_update_user(user_id, data, request, user)
    return schemas.UserOut.model_validate(user_dto)


@users_router.delete("/{user_id}", response_model=dict)
async def delete_user_admin(
    user_id: UUID,
    request: Request,
    # TD-6: same fail-closed SpiceDB check at the route boundary.
    user: models.User = Depends(get_current_admin_user),
    service: UserComplianceService = Depends(get_user_compliance_service),
) -> dict[str, Any]:
    return await service.admin_delete_user(user_id, request, user)


@groups_router.get("", response_model=list[schemas.GroupOut])
async def get_groups(
    service: GroupService = Depends(get_group_service),
) -> list[schemas.GroupOut]:
    groups = await service.get_groups()
    return [schemas.GroupOut.model_validate(g) for g in groups]


router.include_router(users_router)

router.include_router(password_router)
router.include_router(groups_router)
