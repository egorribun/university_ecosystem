import logging

from fastapi import HTTPException, Request, UploadFile, status
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.utils import save_upload
from app.localization import resolve_locale, translate
from app.models import models
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.notifications import create_notifications_for_users
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, audit: AuditService):
        self.audit = audit

    async def update_user_profile(
        self,
        db: AsyncSession,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        update_fields = data.model_dump(exclude_unset=True)
        locale = resolve_locale(request=request, user=user)

        if "email" in update_fields and update_fields["email"] is not None:
            raw_email = str(update_fields["email"]).strip().lower()
            adapter = TypeAdapter(EmailStr)
            try:
                validated_email = adapter.validate_python(raw_email)
            except ValueError as exc:
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

        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}

        for field, value in update_fields.items():
            if field in preferences_fields:
                if not db_user.preferences:
                    db_user.preferences = models.UserPreferences(user_id=db_user.id)
                setattr(db_user.preferences, field, value)
            else:
                setattr(db_user, field, value)
        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        await attach_pending_email(db, db_user)
        return db_user

    async def upload_avatar(
        self,
        db: AsyncSession,
        user: models.User,
        file: UploadFile,
        request: Request,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        url = await save_upload(
            file, "avatars", f"user_{user.id}_avatar", locale=locale
        )
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

    async def upload_cover(
        self,
        db: AsyncSession,
        user: models.User,
        file: UploadFile,
        request: Request,
    ) -> models.User:
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

    async def create_user(
        self,
        db: AsyncSession,
        data: schemas.UserCreate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        locale = resolve_locale(request=request, user=current_user)
        if current_user.role != "admin":
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
                models.InviteCode.is_active.is_(True),
            )
            code_obj = (await db.execute(q)).scalar_one_or_none()
            if not code_obj:
                raise HTTPException(
                    status_code=400,
                    detail=translate("errors.users.invalid_invite", locale=locale),
                )
        user = await crud.create_user(db, data)
        return user

    async def get_users(
        self,
        db: AsyncSession,
        request: Request,
        current_user: models.User,
        full_name: str | None = None,
        search: str | None = None,
        group_id: int | None = None,
        role: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[models.User]:
        locale = resolve_locale(request=request, user=current_user)
        # Allow admins to list all users, or any authenticated user to search
        if current_user.role != "admin" and not search and not full_name:
            raise HTTPException(
                status_code=403,
                detail=translate("errors.forbidden", locale=locale),
            )

        # Use search param as full_name if provided
        name_query = search if search else full_name

        return await crud.get_users(
            db,
            full_name=name_query,
            group_id=group_id,
            role=role,
            limit=limit,
            offset=offset,
        )

    async def admin_update_user(
        self,
        db: AsyncSession,
        user_id: int,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        locale = resolve_locale(request=request, user=current_user)
        if current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail=translate("errors.forbidden", locale=locale),
            )
        updated_user, reset_stats = await crud.admin_update_user(db, user_id, data)
        self.audit.log(
            "users.admin_update",
            request,
            user_id=updated_user.id,
            reason="admin_update",
        )
        if reset_stats is not None:
            if reset_stats.changed:
                # Log MFA reset audit event
                self.audit.log(
                    "users.mfa.reset",
                    request,
                    user_id=updated_user.id,
                    reason="admin_reset",
                )
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
        return updated_user

    async def delete_avatar(
        self,
        db: AsyncSession,
        user: models.User,
    ) -> models.User:
        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)
        db_user.avatar_url = None
        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        return db_user

    async def delete_cover(
        self,
        db: AsyncSession,
        user: models.User,
    ) -> models.User:
        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)
        db_user.cover_url = None
        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        return db_user
