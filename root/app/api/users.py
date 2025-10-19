import hashlib
import json
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import List, Optional

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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.database import get_db
from app.core.observability import get_request_id
from app.localization import resolve_locale, translate
from app.models import models
from app.schemas import schemas
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES, build_reset_email_content
from app.utils.files import delete_static_file
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.users.audit")


router = APIRouter()
password_router = APIRouter(prefix="/password", tags=["password"])
users_router = APIRouter(prefix="/users", tags=["users"])
groups_router = APIRouter(prefix="/groups", tags=["groups"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _redact_sensitive_query(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return "[redacted]"
    redacted_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in {"token", "code"}:
            redacted_items.append((key, "***redacted***"))
        else:
            redacted_items.append((key, value))
    sanitized_query = urlencode(redacted_items, doseq=True)
    sanitized = parts._replace(query=sanitized_query)
    result = urlunsplit(sanitized)
    return result or "[redacted]"


def _send_reset_email(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    mail_from = settings.mail_from or "no-reply@example.com"
    security = (
        settings.smtp_security or ("starttls" if settings.smtp_starttls else "none")
    ).lower()
    subject, plain, html = build_reset_email_content(link, full_name, locale=locale)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    try:
        if not host or not port:
            safe_link = _redact_sensitive_query(link)
            logger.warning(
                "password.reset_email.fallback",
                extra={"email": to_email, "link": safe_link},
            )
            return
        ctx = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        elif security == "starttls":
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except Exception:
        safe_link = _redact_sensitive_query(link)
        logger.error(
            "password.reset_email.error",
            extra={"email": to_email, "link": safe_link},
            exc_info=True,
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
    result = await db.execute(
        select(models.User).where(models.User.email == payload.email)
    )
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=RESET_TOKEN_EXPIRY_MINUTES
        )
        db.add(
            models.PasswordResetToken(
                user_id=user.id, token_hash=token_hash, expires_at=expires, used=False
            )
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
    now = datetime.now(timezone.utc)
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
        expires_at = expires_at.replace(tzinfo=timezone.utc)
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
async def me(user: models.User = Depends(get_current_user)):
    return user


@users_router.put("/me", response_model=schemas.UserOut)
async def update_me(
    data: schemas.UserProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_user = await db.get(models.User, user.id)
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
                models.User.email == validated_email,
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
    return db_user


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
    db_user = await db.get(models.User, user.id)
    db_user.avatar_url = url
    await db.commit()
    await db.refresh(db_user)
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
    db_user = await db.get(models.User, user.id)
    db_user.cover_url = url
    await db.commit()
    await db.refresh(db_user)
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


@users_router.get("", response_model=List[schemas.UserOut])
async def get_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    full_name: Optional[str] = Query(None),
    group_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
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
    return await crud.admin_update_user(db, user_id, data)


@users_router.delete("/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    db_user = await db.get(models.User, user.id)
    if db_user.avatar_url:
        await delete_static_file(db_user.avatar_url)
    db_user.avatar_url = None
    await db.commit()
    await db.refresh(db_user)
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


@groups_router.get("", response_model=List[schemas.GroupOut])
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
    audit_logger.log(level, json.dumps(payload, ensure_ascii=False))
