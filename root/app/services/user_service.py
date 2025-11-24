import logging
from typing import Any

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
from app.services.auth_service import attach_pending_email
from app.services.notifications import create_notifications_for_users
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.users.audit")


def _audit_log(
    event: str,
    request: Request,
    user_id: int | None = None,
    level: int = logging.INFO,
    **kwargs: Any,
) -> None:
    import json

    payload = {
        "event": event,
        "user_id": str(user_id) if user_id else None,
        "ip": request.client.host if request.client else None,
        "path": request.url.path,
        **kwargs,
    }
    audit_logger.log(level, json.dumps(payload), extra=payload)


class UserService:
    @staticmethod
    async def update_user_profile(
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

        for field, value in update_fields.items():
            setattr(db_user, field, value)
        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        await attach_pending_email(db, db_user)
        return db_user

    @staticmethod
    async def upload_avatar(
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

    @staticmethod
    async def upload_cover(
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

    @staticmethod
    async def create_user(
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

    @staticmethod
    async def get_users(
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

    @staticmethod
    async def admin_update_user(
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
        _audit_log(
            "users.admin_update",
            request,
            user_id=updated_user.id,
            reason="admin_update",
        )
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
        return updated_user

    @staticmethod
    async def delete_avatar(
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

    @staticmethod
    async def delete_cover(
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
