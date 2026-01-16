import logging

from fastapi import Request, UploadFile
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.utils import save_upload
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.models import models
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.data_access import export_access_logs, log_data_access
from app.services.notifications import create_notifications_for_users
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession, audit: AuditService) -> None:
        self.db = db
        self.audit = audit

    async def update_user_profile(
        self,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        update_fields = data.model_dump(exclude_unset=True)

        if "email" in update_fields and update_fields["email"] is not None:
            raw_email = str(update_fields["email"]).strip().lower()
            adapter = TypeAdapter(EmailStr)
            try:
                validated_email = adapter.validate_python(raw_email)
            except ValueError as exc:
                raise BusinessRuleViolation("errors.users.invalid_email") from exc

            existing = await self.db.execute(
                select(models.User.id).where(
                    func.lower(models.User.email) == validated_email,
                    models.User.id != user.id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise EntityAlreadyExists("User", validated_email)

            update_fields["email"] = validated_email

        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}

        for field, value in update_fields.items():
            if field in preferences_fields:
                if not db_user.preferences:
                    db_user.preferences = models.UserPreferences(user_id=db_user.id)
                setattr(db_user.preferences, field, value)
            else:
                setattr(db_user, field, value)
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)
        return db_user

    async def upload_avatar(
        self,
        user: models.User,
        file: UploadFile,
        request: Request,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        url = await save_upload(
            file, "avatars", f"user_{user.id}_avatar", locale=locale
        )
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        previous_url = db_user.avatar_url
        db_user.avatar_url = url
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            db_user.avatar_url = previous_url
            await delete_static_file(url)
            raise
        try:
            await self.db.refresh(db_user)
            await ensure_mfa_relationships_loaded(self.db, db_user)
        except Exception:
            db_user.avatar_url = previous_url
            await delete_static_file(url)
            raise
        return db_user

    async def upload_cover(
        self,
        user: models.User,
        file: UploadFile,
        request: Request,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        url = await save_upload(file, "covers", f"user_{user.id}_cover", locale=locale)
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        previous_url = db_user.cover_url
        db_user.cover_url = url
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            db_user.cover_url = previous_url
            await delete_static_file(url)
            raise
        try:
            await self.db.refresh(db_user)
            await ensure_mfa_relationships_loaded(self.db, db_user)
        except Exception:
            db_user.cover_url = previous_url
            await delete_static_file(url)
            raise
        return db_user

    async def create_user(
        self,
        data: schemas.UserCreate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        if current_user.role != "admin":
            raise PermissionDenied()

        if data.role in ["teacher", "admin"]:
            if not data.invite_code:
                raise BusinessRuleViolation("errors.users.invite_required")

            q = select(models.InviteCode).where(
                models.InviteCode.code == data.invite_code,
                models.InviteCode.role == data.role,
                models.InviteCode.is_active.is_(True),
            )
            code_obj = (await self.db.execute(q)).scalar_one_or_none()
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite")

        user = await crud.create_user(self.db, data)
        return user

    async def get_users(
        self,
        request: Request,
        current_user: models.User,
        full_name: str | None = None,
        search: str | None = None,
        group_id: int | None = None,
        role: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[models.User]:
        # Allow admins to list all users, or any authenticated user to search
        if current_user.role != "admin" and not search and not full_name:
            raise PermissionDenied()

        # Use search param as full_name if provided
        name_query = search if search else full_name

        return await crud.get_users(
            self.db,
            full_name=name_query,
            group_id=group_id,
            role=role,
            limit=limit,
            offset=offset,
        )

    async def admin_update_user(
        self,
        user_id: int,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        if current_user.role != "admin":
            raise PermissionDenied()

        updated_user, reset_stats = await crud.admin_update_user(self.db, user_id, data)
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
                    self.db,
                    title=title,
                    body=body,
                    type="security",
                    user_ids=[updated_user.id],
                )
        return updated_user

    async def admin_delete_user(
        self,
        user_id: int,
        request: Request,
        current_user: models.User,
    ) -> dict:
        """Delete a user by admin (anonymize user data)."""

        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.db.get(models.User, user_id, options=USER_MFA_LOAD_OPTIONS)
        if db_user is None:
            raise EntityNotFound("User", user_id)

        # Prevent admin from deleting themselves
        if db_user.id == current_user.id:
            raise BusinessRuleViolation("errors.users.cannot_delete_self")

        anonymized_email = f"deleted+{db_user.id}@deleted.example.com"

        await delete_static_file(db_user.avatar_url) if db_user.avatar_url else None
        await delete_static_file(db_user.cover_url) if db_user.cover_url else None

        db_user.full_name = None
        db_user.email = anonymized_email
        db_user.avatar_url = None
        db_user.cover_url = None
        db_user.about = None
        db_user.telegram = None
        db_user.achievements = None
        db_user.record_book_number = None
        db_user.hashed_password = "deleted"
        db_user.is_active = False
        db_user.status = "deleted"
        db_user.mfa_required = False
        db_user.mfa_default_method = None
        db_user.mfa_last_verified_at = None

        await self.db.execute(
            delete(models.ActiveSession).where(models.ActiveSession.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaChallenge).where(models.MfaChallenge.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaTotpEnrollment).where(
                models.MfaTotpEnrollment.user_id == user_id
            )
        )
        await self.db.execute(
            delete(models.Notification).where(models.Notification.user_id == user_id)
        )
        await self.db.execute(
            delete(models.DataAccessLog).where(
                or_(
                    models.DataAccessLog.actor_user_id == user_id,
                    models.DataAccessLog.subject_user_id == user_id,
                )
            )
        )

        db_user.preferences = None
        db_user.spotify = None

        self.audit.log(
            "users.admin_delete", request, user_id=user_id, reason="admin_delete"
        )

        await self.db.commit()
        return {"deleted": True, "user_id": user_id}

    async def delete_avatar(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)
        db_user.avatar_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def delete_cover(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)
        db_user.cover_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)

        profile = schemas.UserOut.from_orm(db_user).model_dump()

        sessions_result = await self.db.execute(
            select(models.ActiveSession).where(models.ActiveSession.user_id == user.id)
        )
        sessions = [
            {
                "id": session.id,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
                "revoked_at": session.revoked_at,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "last_seen_at": session.last_seen_at,
                "mfa_completed_at": session.mfa_completed_at,
            }
            for session in sessions_result.scalars()
        ]

        notifications_result = await self.db.execute(
            select(models.Notification).where(models.Notification.user_id == user.id)
        )
        notifications = [
            {
                "id": item.id,
                "title": item.title,
                "body": item.body,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in notifications_result.scalars()
        ]

        challenges = [
            {
                "id": challenge.id,
                "type": challenge.challenge_type,
                "expires_at": challenge.expires_at,
                "consumed_at": challenge.consumed_at,
                "created_at": challenge.created_at,
            }
            for challenge in db_user.mfa_challenges
        ]

        enrollments = [
            {
                "id": enrollment.id,
                "label": enrollment.label,
                "is_active": enrollment.is_active,
                "confirmed_at": enrollment.confirmed_at,
                "revoked_at": enrollment.revoked_at,
                "created_at": enrollment.created_at,
            }
            for enrollment in db_user.totp_enrollments
        ]

        access_logs = await export_access_logs(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            limit=2000,
        )
        access_log_payload = [
            {
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "action": log.action,
                "created_at": log.created_at,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "context": log.context,
            }
            for log in access_logs
        ]

        self.audit.log("users.data_export", request, user_id=user.id)
        await log_data_access(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="export",
            request=request,
        )

        return schemas.DataExportOut(
            profile=profile,
            sessions=sessions,
            notifications=notifications,
            mfa_challenges=challenges,
            mfa_enrollments=enrollments,
            access_logs=access_log_payload,
        )

    async def delete_user_data(
        self,
        user: models.User,
        request: Request,
        *,
        confirm: bool,
    ) -> schemas.DataDeletionOut:
        if not confirm:
            raise BusinessRuleViolation("errors.users.confirmation_required")

        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        if not db_user:
            raise EntityNotFound("User", user.id)
        anonymized_email = f"deleted+{user.id}@deleted.example.com"

        await delete_static_file(db_user.avatar_url) if db_user.avatar_url else None
        await delete_static_file(db_user.cover_url) if db_user.cover_url else None

        db_user.full_name = None
        db_user.email = anonymized_email
        db_user.avatar_url = None
        db_user.cover_url = None
        db_user.about = None
        db_user.telegram = None
        db_user.achievements = None
        db_user.record_book_number = None
        db_user.hashed_password = "deleted"
        db_user.is_active = False
        db_user.status = "deleted"
        db_user.mfa_required = False
        db_user.mfa_default_method = None
        db_user.mfa_last_verified_at = None

        await self.db.execute(
            delete(models.ActiveSession).where(models.ActiveSession.user_id == user.id)
        )
        await self.db.execute(
            delete(models.MfaChallenge).where(models.MfaChallenge.user_id == user.id)
        )
        await self.db.execute(
            delete(models.MfaTotpEnrollment).where(
                models.MfaTotpEnrollment.user_id == user.id
            )
        )
        await self.db.execute(
            delete(models.Notification).where(models.Notification.user_id == user.id)
        )
        await self.db.execute(
            delete(models.DataAccessLog).where(
                or_(
                    models.DataAccessLog.actor_user_id == user.id,
                    models.DataAccessLog.subject_user_id == user.id,
                )
            )
        )

        db_user.preferences = None
        db_user.spotify = None

        self.audit.log("users.data_delete", request, user_id=user.id)
        await log_data_access(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="delete",
            request=request,
        )

        await self.db.commit()
        await self.db.refresh(db_user)
        return schemas.DataDeletionOut(deleted=True, anonymized_email=anonymized_email)
