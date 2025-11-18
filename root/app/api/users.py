import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
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
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user, require_fresh_mfa
from app.api.utils import save_upload
from app.auth.security import get_password_hash, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.core.observability import get_request_id
from app.localization import resolve_locale, translate
from app.models import models
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services.notifications import create_notifications_for_users
from app.services.session_cleanup import revoke_sessions_matching
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES, send_reset_email
from app.utils.files import delete_static_file
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.users.audit")


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
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid client input
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
            detail=translate(
                "errors.profile_cache.invalid_signature", locale=locale
            ),
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
            detail=translate(
                "errors.profile_cache.invalid_signature", locale=locale
            ),
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _prepare_password_reset_token(
    db: AsyncSession,
    user: models.User,
    *,
    token_hash: str,
    expires_at: datetime,
) -> None:
    max_active = max(1, int(settings.password_reset_max_active_tokens))
    result = await db.execute(
        select(models.PasswordResetToken)
        .where(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used.is_(False),
        )
        .order_by(
            models.PasswordResetToken.created_at.desc(),
            models.PasswordResetToken.id.desc(),
        )
    )
    active_tokens = list(result.scalars())

    for stale in active_tokens[max_active:]:
        stale.used = True

    if len(active_tokens) >= max_active:
        target = active_tokens[max_active - 1]
        target.token_hash = token_hash
        target.expires_at = expires_at
        target.used = False
        target.created_at = datetime.now(UTC)
        return

    record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        used=False,
    )
    db.add(record)


async def _get_active_email_change_request(
    db: AsyncSession, user_id: int
) -> models.EmailChangeToken | None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(models.EmailChangeToken)
        .where(
            models.EmailChangeToken.user_id == user_id,
            models.EmailChangeToken.used.is_(False),
            models.EmailChangeToken.expires_at > now,
        )
        .order_by(models.EmailChangeToken.created_at.desc())
    )
    return result.scalars().first()


async def _attach_pending_email(
    db: AsyncSession, user: models.User | None
) -> models.User | None:
    if user is None:
        return None
    pending = await _get_active_email_change_request(db, user.id)
    setattr(user, "pending_email", pending.new_email if pending else None)
    return user


async def _create_email_change_request(
    db: AsyncSession, user: models.User, new_email: str
) -> tuple[models.EmailChangeToken, str]:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

    await db.execute(
        update(models.EmailChangeToken)
        .where(
            models.EmailChangeToken.user_id == user.id,
            models.EmailChangeToken.used.is_(False),
        )
        .values(used=True)
    )

    record = models.EmailChangeToken(
        user_id=user.id,
        new_email=new_email,
        token_hash=token_hash,
        expires_at=expires,
        used=False,
    )
    db.add(record)
    await db.flush()
    return record, token


def _send_reset_email_blocking(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    send_reset_email(to_email, link, full_name, locale=locale)


async def _send_reset_email(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    await anyio.to_thread.run_sync(
        _send_reset_email_blocking,
        to_email,
        link,
        full_name,
        locale,
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
):
    normalized_email = payload.email.strip().lower()
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == normalized_email)
    )
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        await _prepare_password_reset_token(
            db,
            user,
            token_hash=token_hash,
            expires_at=expires,
        )
        await db.commit()
        base = settings.app_base_url_clean
        reset_link = f"{base}/reset-password?token={token}"
        locale = resolve_locale(request=request, user=user)
        bg.add_task(
            _send_reset_email,
            user.email,
            reset_link,
            user.full_name or "",
            locale,
        )
        _audit_log(
            "password.reset.initiated",
            request,
            user_id=user.id,
            reason="initiated",
        )
    else:
        _audit_log(
            "password.reset.initiated",
            request,
            level=logging.WARNING,
            reason="user_not_found",
        )
    return {"ok": True}


@password_router.post(
    "/reset",
    dependencies=[Depends(sensitive_route_limit())],
)
async def reset_password(
    payload: schemas.ResetPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    token_hash = _hash_token(payload.token)
    result = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == token_hash,
            models.PasswordResetToken.used.is_(False),  # E712 -> .is_(False)
        )
    )
    rec = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if not rec:
        _audit_log(
            "password.reset.failed",
            request,
            level=logging.WARNING,
            reason="token_invalid",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.password.invalid_or_expired_link", locale=locale),
        )
    expires_at = rec.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        _audit_log(
            "password.reset.failed",
            request,
            level=logging.WARNING,
            user_id=rec.user_id,
            reason="token_expired",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.password.invalid_or_expired_link", locale=locale),
        )
    user = await db.get(models.User, rec.user_id)
    if not user or not getattr(user, "is_active", True):
        _audit_log(
            "password.reset.failed",
            request,
            level=logging.WARNING,
            user_id=rec.user_id,
            reason="user_inactive",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.password.invalid_link", locale=locale),
        )
    try:
        user.hashed_password = get_password_hash(payload.password, locale=locale)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    rec.used = True
    await db.execute(
        update(models.PasswordResetToken)
        .where(
            models.PasswordResetToken.user_id == rec.user_id,
            models.PasswordResetToken.used.is_(False),  # E712 -> .is_(False)
        )
        .values(used=True)
    )
    await db.commit()
    _audit_log(
        "password.reset.completed",
        request,
        user_id=rec.user_id,
        reason="completed",
    )
    return {"ok": True}


@users_router.get("/me", response_model=schemas.UserOut)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _enforce_profile_cache_integrity(request)
    await _attach_pending_email(db, user)
    return user


@users_router.put("/me", response_model=schemas.UserOut)
async def update_me(
    data: schemas.UserProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    update_fields = data.model_dump(exclude_unset=True)
    locale = resolve_locale(request=request, user=user)

    if "email" in update_fields and update_fields["email"] is not None:
        raw_email = str(update_fields["email"]).strip().lower()
        adapter = TypeAdapter(EmailStr)
        try:
            validated_email = adapter.validate_python(raw_email)
        except (
            ValueError
        ) as exc:  # pragma: no cover - defensive, TypeAdapter raises ValueError
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.invalid_email", locale=locale),
            ) from exc

        existing = await db.execute(
            select(models.User.id).where(
                func.lower(models.User.email) == validated_email,
                models.User.id != user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.email_in_use", locale=locale),
            )

        update_fields["email"] = validated_email

    for field, value in update_fields.items():
        setattr(db_user, field, value)
    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    await _attach_pending_email(db, db_user)
    return db_user


@users_router.post("/me/email", response_model=schemas.UserOut)
async def change_email(
    payload: schemas.UserEmailChangeIn,
    request: Request,
    bg: BackgroundTasks,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.invalid_password", locale=locale),
        )

    normalized_email = str(payload.email).strip().lower()
    adapter = TypeAdapter(EmailStr)
    try:
        validated_email = adapter.validate_python(normalized_email)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.invalid_email", locale=locale),
        ) from exc

    if validated_email == user.email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.email_same", locale=locale),
        )

    existing = await db.execute(
        select(models.User.id).where(
            func.lower(models.User.email) == validated_email,
            models.User.id != user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.email_in_use", locale=locale),
        )

    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    _, token = await _create_email_change_request(db, db_user, validated_email)

    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    await _attach_pending_email(db, db_user)
    await _attach_pending_email(db, user)

    base = settings.app_base_url_clean
    confirm_link = f"{base}/settings/email-confirm?token={token}"
    bg.add_task(
        _send_reset_email,
        validated_email,
        confirm_link,
        user.full_name or "",
        locale,
    )

    _audit_log(
        "users.email.change_requested",
        request,
        user_id=user.id,
        reason="pending_confirmation",
        extra={"email": validated_email},
    )
    return db_user


@users_router.post("/me/email/confirm", response_model=schemas.UserOut)
async def confirm_email_change(
    payload: schemas.UserEmailConfirmIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    token_hash = _hash_token(payload.token)
    now = datetime.now(UTC)

    result = await db.execute(
        select(models.EmailChangeToken).where(
            models.EmailChangeToken.token_hash == token_hash
        )
    )
    record = result.scalar_one_or_none()
    if record is None or record.user_id != user.id or record.used:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.email_confirmation_invalid", locale=locale),
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.email_confirmation_invalid", locale=locale),
        )

    existing = await db.execute(
        select(models.User.id).where(
            func.lower(models.User.email) == record.new_email,
            models.User.id != user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        record.used = True
        await db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user.id,
                models.EmailChangeToken.id != record.id,
            )
            .values(used=True)
        )
        await db.commit()
        await _attach_pending_email(db, user)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.email_confirmation_conflict", locale=locale),
        )

    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    db_user.email = record.new_email
    await db.execute(
        update(models.EmailChangeToken)
        .where(models.EmailChangeToken.id == record.id)
        .values(used=True)
    )
    await db.execute(
        update(models.EmailChangeToken)
        .where(
            models.EmailChangeToken.user_id == user.id,
            models.EmailChangeToken.id != record.id,
        )
        .values(used=True)
    )

    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    await _attach_pending_email(db, db_user)
    await _attach_pending_email(db, user)
    user.email = record.new_email

    _audit_log(
        "users.email.changed",
        request,
        user_id=user.id,
        reason="confirmed",
        extra={"email": record.new_email},
    )
    return db_user


@users_router.post("/me/password", response_model=schemas.PasswordChangeOut)
async def change_password(
    payload: schemas.UserPasswordChangeIn,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.invalid_password", locale=locale),
        )
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.users.password_same", locale=locale),
        )
    try:
        hashed_password = get_password_hash(payload.new_password, locale=locale)
    except ValueError as exc:  # pragma: no cover - policy should raise ValueError
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    db_user.hashed_password = hashed_password

    active_session: models.ActiveSession | None = getattr(
        request.state, "active_session", None
    )
    current_session_id = active_session.id if active_session else None
    conditions = [
        models.ActiveSession.user_id == user.id,
        models.ActiveSession.revoked_at.is_(None),
    ]
    if current_session_id is not None:
        conditions.append(models.ActiveSession.id != current_session_id)
    revoked = await revoke_sessions_matching(db=db, whereclause=and_(*conditions))

    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    user.hashed_password = hashed_password
    _audit_log(
        "users.password.changed",
        request,
        user_id=user.id,
        reason="user_update",
        extra={"revoked_sessions": revoked},
    )
    return schemas.PasswordChangeOut(ok=True, revoked_sessions=revoked)


@users_router.post("/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    url = await save_upload(file, "avatars", f"user_{user.id}_avatar", locale=locale)
    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    previous_url = db_user.avatar_url
    db_user.avatar_url = url
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        db_user.avatar_url = previous_url
        await delete_static_file(url)
        raise
    try:
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
    except Exception:
        db_user.avatar_url = previous_url
        await delete_static_file(url)
        raise
    return db_user


@users_router.post("/me/cover", response_model=schemas.UserOut)
async def upload_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    url = await save_upload(file, "covers", f"user_{user.id}_cover", locale=locale)
    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    previous_url = db_user.cover_url
    db_user.cover_url = url
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        db_user.cover_url = previous_url
        await delete_static_file(url)
        raise
    try:
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
    except Exception:
        db_user.cover_url = previous_url
        await delete_static_file(url)
        raise
    return db_user


@users_router.post("", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    if data.role in ["teacher", "admin"]:
        if not data.invite_code:
            raise HTTPException(
                status_code=400,
                detail=translate("errors.users.invite_required", locale=locale),
            )
        q = select(models.InviteCode).where(
            models.InviteCode.code == data.invite_code,
            models.InviteCode.role == data.role,
            models.InviteCode.is_active.is_(True),  # E712 -> .is_(True)
        )
        code_obj = (await db.execute(q)).scalar_one_or_none()
        if not code_obj:
            raise HTTPException(
                status_code=400,
                detail=translate("errors.users.invalid_invite", locale=locale),
            )
    user = await crud.create_user(db, data)
    return user


@users_router.get("", response_model=list[schemas.UserOut])
async def get_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    full_name: str | None = Query(None),
    group_id: int | None = Query(None),
    role: str | None = Query(None),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    return await crud.get_users(db, full_name=full_name, group_id=group_id, role=role)


@users_router.patch("/{user_id}", response_model=schemas.UserOut)
async def update_user_admin(
    user_id: int,
    data: schemas.UserAdminUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    updated_user, reset_stats = await crud.admin_update_user(db, user_id, data)
    _audit_log(
        "users.admin_update", request, user_id=updated_user.id, reason="admin_update"
    )
    reset_requested = bool(getattr(data, "reset_mfa", False))
    if reset_stats is not None:
        if reset_stats.changed:
            target_locale = resolve_locale(request=request, user=updated_user)
            title = translate("notifications.mfa.reset.title", locale=target_locale)
            body = translate("notifications.mfa.reset.body", locale=target_locale)
            await create_notifications_for_users(
                db,
                title=title,
                body=body,
                type="security",
                user_ids=[updated_user.id],
            )
            _audit_log(
                "users.mfa.reset",
                request,
                user_id=updated_user.id,
                reason="admin_reset",
            )
        else:
            _audit_log(
                "users.mfa.reset",
                request,
                user_id=updated_user.id,
                reason="admin_reset_noop",
            )
    elif reset_requested:
        _audit_log(
            "users.mfa.reset",
            request,
            user_id=updated_user.id,
            reason="admin_reset_requested_noop",
        )
    return updated_user


@users_router.get("/{user_id}/mfa", response_model=schemas.UserMfaMethodsOut)
async def get_user_mfa_methods(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    target_user = await db.get(models.User, user_id)
    if target_user is None:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.users.not_found", locale=locale),
        )
    totp_rows = await db.execute(
        select(models.MfaTotpEnrollment)
        .where(models.MfaTotpEnrollment.user_id == user_id)
        .where(models.MfaTotpEnrollment.is_active.is_(True))
        .where(models.MfaTotpEnrollment.confirmed_at.is_not(None))
        .order_by(models.MfaTotpEnrollment.created_at)
    )
    recovery_rows = await db.execute(
        select(models.MfaRecoveryCode)
        .where(models.MfaRecoveryCode.user_id == user_id)
        .order_by(models.MfaRecoveryCode.created_at)
    )
    challenge_rows = await db.execute(
        select(models.MfaChallenge)
        .where(models.MfaChallenge.user_id == user_id)
        .where(models.MfaChallenge.consumed_at.is_(None))
        .order_by(models.MfaChallenge.created_at)
    )
    _audit_log("users.mfa.inspect", request, user_id=user_id, reason="admin_view")
    return schemas.UserMfaMethodsOut(
        totp_enrollments=list(totp_rows.scalars().all()),
        recovery_codes=list(recovery_rows.scalars().all()),
        pending_challenges=list(challenge_rows.scalars().all()),
    )


@users_router.delete("/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    if db_user.avatar_url:
        await delete_static_file(db_user.avatar_url)
    db_user.avatar_url = None
    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    return db_user


@users_router.delete("/me/cover", response_model=schemas.UserOut)
async def delete_cover(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
    if db_user.cover_url:
        await delete_static_file(db_user.cover_url)
    db_user.cover_url = None
    await db.commit()
    await db.refresh(db_user)
    await ensure_mfa_relationships_loaded(db, db_user)
    return db_user


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    if user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail=translate("errors.users.cannot_delete_self", locale=locale),
        )
    await crud.delete_user(db, user_id)
    return None


@groups_router.post("", response_model=schemas.GroupOut)
async def create_group(
    data: schemas.GroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    return await crud.create_group(db, data)


@groups_router.get("", response_model=list[schemas.GroupOut])
async def get_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Group))
    return result.scalars().all()


router.include_router(password_router)
router.include_router(users_router)
router.include_router(groups_router)


__all__ = ["router"]


def _audit_log(
    event: str,
    request: Request,
    *,
    level: int = logging.INFO,
    user_id: int | str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    request_id = get_request_id() or request.headers.get("x-request-id")
    client_ip = request.client.host if request.client else None
    payload: dict[str, str] = {"event": event}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    if request_id:
        payload["request_id"] = request_id
    if client_ip:
        payload["ip"] = client_ip
    if reason:
        payload["reason"] = reason
    if extra:
        payload.update({str(key): str(value) for key, value in extra.items()})
    audit_logger.log(level, json.dumps(payload, ensure_ascii=False))
