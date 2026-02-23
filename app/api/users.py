import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import (
    get_current_user,
    get_current_user_full,
    require_fresh_mfa,
)
from app.api.validation import raise_validation_error, require_admin
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
from app.core.rate_limit import sensitive_route_limit
from app.models import models
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.data_access import (
    batch_log_data_access,
    export_access_logs,
    log_data_access,
    serialize_access_logs_csv,
)
from app.services.group_service import GroupService
from app.services.notifications import create_notifications_for_users
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService

# Export for test compatibility
__all__ = ["create_notifications_for_users"]

logger = logging.getLogger(__name__)

router = APIRouter()
password_router = APIRouter(prefix="/password", tags=["password"])
users_router = APIRouter(prefix="/users", tags=["users"])
groups_router = APIRouter(prefix="/groups", tags=["groups"])

PROFILE_CACHE_HEADER = "x-profile-cache-envelope"


def _enforce_profile_cache_integrity(request: Request) -> None:
    raw_envelope = request.headers.get(PROFILE_CACHE_HEADER)
    if not raw_envelope:
        return

    locale = resolve_locale(request=request)
    session = getattr(request.state, "active_session", None)
    if session is None or not getattr(session, "signing_key", None):
        raise_validation_error("errors.sessions.signing_key_missing", locale)

    try:
        candidate = json.loads(raw_envelope)
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
        str(getattr(session, "signing_key", "")).encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(digest).decode("ascii")

    if not hmac.compare_digest(signature, expected_signature):
        raise_validation_error("errors.profile_cache.invalid_signature", locale)


@password_router.post(
    "/forgot",
    dependencies=[Depends(sensitive_route_limit())],
)
async def forgot_password(
    payload: schemas.ForgotPasswordIn,
    request: Request,
    bg: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
):
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
):
    await auth_service.perform_password_reset(payload.token, payload.password, request)
    return {"ok": True}


@users_router.get("/me", response_model=schemas.UserOut, summary="Me")
async def me(
    request: Request,
    db: AsyncSession = Depends(get_read_db),
    user: models.User = Depends(get_current_user_full),
    auth_service: AuthService = Depends(get_auth_service),
):
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


@users_router.put("/me", response_model=schemas.UserOut, summary="Update Me")
async def update_me(
    data: schemas.UserProfileUpdate,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserProfileService = Depends(get_user_profile_service),
):
    return await service.update_user_profile(user, data, request)


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
):
    return await auth_service.initiate_email_change(user, payload, request, bg)


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
):
    return await auth_service.confirm_email_change(user, payload.token, request)


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
):
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
):
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
):
    return await service.delete_user_data(user, request, confirm=payload.confirm)


@users_router.post("/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
):
    return await service.upload_avatar(user, file)


@users_router.post("/me/cover", response_model=schemas.UserOut)
async def upload_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
):
    return await service.upload_cover(user, file)


@users_router.delete("/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
):
    return await service.delete_avatar(user)


@users_router.delete("/me/cover", response_model=schemas.UserOut)
async def delete_cover(
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserMediaService = Depends(get_user_media_service),
):
    return await service.delete_cover(user)


@users_router.post("", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    request: Request,
    user: UserAuthDTO = Depends(deps.get_current_user_auth_dto),
    service: UserComplianceService = Depends(get_user_compliance_service),
):
    return await service.create_user(data, request, user)


@users_router.get(
    "",
    response_model=list[schemas.UserPublicOut | schemas.UserOut],
    summary="Search Users",
)
async def get_users(
    request: Request,
    filters: schemas.UserSearchFilter = Depends(),
    current_user: UserDTO = Depends(deps.get_current_user_dto),
    service: UserProfileService = Depends(get_user_profile_service),
    db: AsyncSession = Depends(get_read_db),
):
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
    await batch_log_data_access(db, entries=log_entries, request=request)

    if current_user.role != "admin":
        # Force strict serialization to public schema for non-admins
        return [
            schemas.UserPublicOut.model_validate(u, from_attributes=True) for u in users
        ]

    # Admins get full objects
    return users


@users_router.get("/audit/export")
async def export_access_audit(
    request: Request,
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    db: AsyncSession = Depends(get_read_db),
    user: models.User = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    logs = await export_access_logs(db, start_at=start_at, end_at=end_at, limit=20_000)
    audit.log("users.audit.export", request, user_id=user.id)
    csv_payload = serialize_access_logs_csv(logs)
    return Response(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=access_audit.csv"},
    )


@users_router.patch("/{user_id}", response_model=schemas.UserOut)
async def update_user_admin(
    user_id: UUID,
    data: schemas.UserAdminUpdate,
    request: Request,
    user: models.User = Depends(get_current_user),
    service: UserProfileService = Depends(get_user_profile_service),
):
    return await service.admin_update_user(user_id, data, request, user)  # type: ignore[arg-type]


@users_router.delete("/{user_id}", response_model=dict)
async def delete_user_admin(
    user_id: UUID,
    request: Request,
    user: models.User = Depends(get_current_user),
    service: UserComplianceService = Depends(get_user_compliance_service),
):
    return await service.admin_delete_user(user_id, request, user)  # type: ignore[arg-type]


@groups_router.get("", response_model=list[schemas.GroupOut])
async def get_groups(
    service: GroupService = Depends(get_group_service),
):
    return await service.get_groups()


router.include_router(users_router)

router.include_router(password_router)
router.include_router(groups_router)
