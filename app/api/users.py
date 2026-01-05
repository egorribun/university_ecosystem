import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_audit_service,
    get_auth_service,
    get_current_user,
    get_user_service,
    require_fresh_mfa,
)
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.models import models
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, attach_pending_email
from app.services.data_access import (
    batch_log_data_access,
    export_access_logs,
    log_data_access,
    serialize_access_logs_csv,
)
from app.services.notifications import create_notifications_for_users
from app.services.user_service import UserService
from app.utils.ratelimit import sensitive_route_limit

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.sessions.signing_key_missing", locale=locale),
        )

    try:
        candidate = json.loads(raw_envelope)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.profile_cache.invalid_envelope", locale=locale),
        ) from exc

    if not isinstance(candidate, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.profile_cache.invalid_envelope", locale=locale),
        )

    signature = candidate.get("signature")
    if not isinstance(signature, str) or not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.profile_cache.invalid_signature", locale=locale),
        )

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.profile_cache.invalid_envelope", locale=locale),
        )

    payload_json = json.dumps(payload, separators=(",", ":"))
    digest = hmac.new(
        session.signing_key.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(digest).decode("ascii")

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.profile_cache.invalid_signature", locale=locale),
        )


@password_router.post(
    "/forgot",
    dependencies=[Depends(sensitive_route_limit())],
)
async def forgot_password(
    payload: schemas.ForgotPasswordIn,
    request: Request,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.initiate_password_reset(db, payload.email, request, bg)
    return {"ok": True}


@password_router.post(
    "/reset",
    dependencies=[Depends(sensitive_route_limit())],
)
async def reset_password(
    payload: schemas.ResetPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.perform_password_reset(
        db, payload.token, payload.password, request
    )
    return {"ok": True}


@users_router.get("/me", response_model=schemas.UserOut)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _enforce_profile_cache_integrity(request)
    await attach_pending_email(db, user)
    await log_data_access(
        db,
        actor_user_id=user.id,
        subject_user_id=user.id,
        resource_type="profile",
        resource_id=str(user.id),
        action="read",
        request=request,
    )
    return user


@users_router.put("/me", response_model=schemas.UserOut)
async def update_me(
    data: schemas.UserProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.update_user_profile(db, user, data, request)


@users_router.post(
    "/me/email",
    response_model=schemas.UserOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def change_email(
    payload: schemas.UserEmailChangeIn,
    request: Request,
    bg: BackgroundTasks,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.initiate_email_change(db, user, payload, request, bg)


@users_router.post(
    "/me/email/confirm",
    response_model=schemas.UserOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def confirm_email_change(
    payload: schemas.UserEmailConfirmIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.confirm_email_change(db, user, payload.token, request)


@users_router.post(
    "/me/password",
    response_model=schemas.PasswordChangeOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def change_password(
    payload: schemas.UserPasswordChangeIn,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    ok, revoked = await auth_service.change_password(db, user, payload, request)
    return schemas.PasswordChangeOut(ok=ok, revoked_sessions=revoked)


@users_router.post(
    "/me/export",
    response_model=schemas.DataExportOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def export_me(
    request: Request,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.export_user_data(db, user, request)


@users_router.post(
    "/me/delete",
    response_model=schemas.DataDeletionOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def delete_me(
    payload: schemas.DataDeletionRequest,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.delete_user_data(db, user, request, confirm=payload.confirm)


@users_router.post("/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.upload_avatar(db, user, file, request)


@users_router.post("/me/cover", response_model=schemas.UserOut)
async def upload_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.upload_cover(db, user, file, request)


@users_router.delete("/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.delete_avatar(db, user)


@users_router.delete("/me/cover", response_model=schemas.UserOut)
async def delete_cover(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.delete_cover(db, user)


@users_router.post("", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.create_user(db, data, request, user)


@users_router.get("", response_model=list[schemas.UserOut])
async def get_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    full_name: str | None = Query(None),
    search: str | None = Query(None),
    group_id: int | None = Query(None),
    role: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    users = await service.get_users(
        db,
        request,
        user,
        full_name=full_name,
        search=search,
        group_id=group_id,
        role=role,
        limit=limit,
        offset=offset,
    )
    log_entries = [
        {
            "actor_user_id": user.id,
            "subject_user_id": item.id,
            "resource_type": "profile",
            "resource_id": str(item.id),
            "action": "read",
        }
        for item in users
    ]
    await batch_log_data_access(db, entries=log_entries, request=request)
    return users


@users_router.get("/audit/export")
async def export_access_audit(
    request: Request,
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
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
    user_id: int,
    data: schemas.UserAdminUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.admin_update_user(db, user_id, data, request, user)


@users_router.delete("/{user_id}", response_model=dict)
async def delete_user_admin(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.admin_delete_user(db, user_id, request, user)


@groups_router.get("", response_model=list[schemas.GroupOut])
async def get_groups(
    db: AsyncSession = Depends(get_db),
):
    from app import crud

    groups = await crud.get_groups(db)
    return groups


router.include_router(users_router)

router.include_router(password_router)
router.include_router(groups_router)
