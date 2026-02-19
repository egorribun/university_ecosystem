import logging

from fastapi import Request, UploadFile

from app.api.utils import save_upload
from app.auth import mfa
from app.auth.security import _validate_password_hibp, get_password_hash
from app.core.config import settings
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.audit_service import AuditService, SecurityEvent, auditable
from app.services.auth_service import attach_pending_email
from app.services.data_access import log_data_access
from app.services.notification_service import NotificationService
from app.services.user.logic import anonymize_user_data, update_user_attributes
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.repo = user_repo
        self.audit = audit
        self.notifications = notifications

    async def get_user_by_id(self, user_id: int) -> models.User | None:
        return await self.repo.get(user_id)

    async def get_user_by_email(self, email: str) -> models.User | None:
        return await self.repo.get_by_email(email)

    @auditable(SecurityEvent.USER_PROFILE_UPDATE, user_id_param="user")
    async def update_user_profile(
        self,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        """Update current user profile (self-update)."""
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        payload = data.model_dump(exclude_unset=True)

        if "email" in payload and payload["email"] is not None:
            from app.services.user.logic import validate_user_email

            payload["email"] = await validate_user_email(
                self.repo, payload["email"], exclude_user_id=user.id
            )

        if hasattr(db_user, "profile") and db_user.profile:
            # Manually update profile fields if they are in payload
            profile_fields = {
                "first_name",
                "last_name",
                "bio",
                "phone_number",
                "website",
                "location",
            }
            for field in profile_fields:
                if field in payload:
                    setattr(db_user.profile, field, payload.pop(field))

        # Update remaining user fields
        update_user_attributes(db_user, payload)

        await self.repo.commit()
        await self.repo.refresh(db_user)
        # Ensure relationships loaded for schema validation
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        await attach_pending_email(self.repo.db, db_user)

        return db_user

    async def get_users(
        self,
        request: Request,
        current_user: models.User | None = None,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[models.User]:
        """Admin list users."""
        filters = filters or schemas.UserSearchFilter()

        # Check permissions if current_user provided (for admin endpoint)
        # If no current_user (internal call?), skip check or require it?
        # Based on test_get_users_non_admin_no_search, it expects permission check.

        if current_user and (
            current_user.role != "admin"
            and not filters.search
            and not filters.full_name
        ):
            raise PermissionDenied()

        # Clean name query
        name_query = filters.full_name
        if name_query:
            name_query = name_query.strip()
            if not name_query:
                name_query = None

        # We update filters with the name query for repository call
        filters.full_name = name_query
        return await self.repo.list_users(filters=filters)

    @auditable(SecurityEvent.ADMIN_USER_MODIFY, user_id_param="user_id")
    async def admin_update_user(
        self,
        user_id: int,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.repo.get(user_id)
        if not db_user:
            raise EntityNotFound("User", user_id)

        payload = data.model_dump(exclude_unset=True)
        reset_requested = bool(payload.pop("reset_mfa", False))

        if "email" in payload and payload["email"] is not None:
            payload["email"] = str(payload["email"]).strip().lower()

        # Update fields logic matching crud
        update_user_attributes(db_user, payload)

        reset_stats = None
        if reset_requested:
            reset_stats = await mfa.reset_user_mfa(self.repo.db, user=db_user)

        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)

        updated_user = db_user

        if reset_stats is not None and reset_stats.changed:
            # Log MFA reset audit event (Manual for now as it's a side-effect)
            self.audit.log(
                "users.mfa.reset",
                request,
                user_id=updated_user.id,
                reason="admin_reset",
            )
            target_locale = resolve_locale(request=request, user=updated_user)
            title = translate("notifications.mfa.reset.title", locale=target_locale)
            body = translate("notifications.mfa.reset.body", locale=target_locale)
            await self.notifications.send_security_notification(
                user_ids=[updated_user.id],
                title=title,
                body=body,
            )
        return updated_user

    @auditable(SecurityEvent.ADMIN_USER_DELETE, user_id_param="user_id")
    async def admin_delete_user(
        self,
        user_id: int,
        request: Request,
        current_user: models.User,
    ) -> dict:
        """Delete a user by admin (anonymize user data)."""

        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.repo.get(user_id)
        if db_user is None:
            raise EntityNotFound("User", user_id)

        # Prevent admin from deleting themselves
        if db_user.id == current_user.id:
            raise BusinessRuleViolation("errors.users.cannot_delete_self")

        await anonymize_user_data(db_user)

        await self.repo.commit()
        return {"deleted": True, "user_id": user_id}

    async def delete_avatar(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)
        if db_user.profile:
            db_user.profile.avatar_url = None
        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        return db_user

    async def delete_cover(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)
        if db_user.profile:
            db_user.profile.cover_url = None
        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        return db_user

    @auditable("users.data_export", user_id_param="user")
    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        await attach_pending_email(self.repo.db, db_user)

        profile = schemas.UserOut.model_validate(db_user).model_dump()

        # Sessions
        sessions_list = await self.repo.get_user_sessions(user.id)
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
            for session in sessions_list
        ]

        # Notifications
        notifications_list = await self.repo.get_user_notifications(user.id)
        notifications = [
            {
                "id": item.id,
                "title": item.title,
                "body": item.body,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in notifications_list
        ]

        # MFA challenges directly from relationship
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

        access_logs = await self.repo.get_user_access_logs(user.id, limit=2000)
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

        await log_data_access(
            self.repo.db,
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

    @auditable(SecurityEvent.USER_DELETE, user_id_param="user")
    async def delete_user_data(
        self,
        user: models.User,
        request: Request,
        *,
        confirm: bool,
    ) -> schemas.DataDeletionOut:
        if not confirm:
            raise BusinessRuleViolation("errors.users.confirmation_required")

        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(user.id)
        await log_data_access(
            self.repo.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="delete",
            request=request,
        )

        await self.repo.commit()
        await self.repo.refresh(db_user)
        return schemas.DataDeletionOut(deleted=True, anonymized_email=db_user.email)

    async def register_user(
        self,
        user_in: schemas.UserCreate,
    ) -> models.User:
        """Register a new user (public signup)."""
        raw_role = getattr(user_in, "role", None)
        from app.models.enums import UserRole

        requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT
        normalized_email = user_in.email.strip().lower()

        code = None
        if hasattr(user_in, "invite_code") and requested_role in (
            UserRole.TEACHER,
            UserRole.ADMIN,
        ):
            code_obj = await self.repo.get_invite_code(user_in.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite")

            if (
                code_obj.role != requested_role.value
                or not code_obj.is_active
                or code_obj.is_used
            ):
                raise BusinessRuleViolation("errors.users.invalid_invite")
            code = code_obj

        if await self.repo.check_email_exists(normalized_email):
            raise EntityAlreadyExists("User", normalized_email)

        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(user_in.password)
        hashed_password = await get_password_hash(user_in.password)

        user_data = user_in.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed_password
        user_data["role"] = requested_role.value
        user_data["email"] = normalized_email
        if "id" in user_data:
            del user_data["id"]

        user_data["mfa_required"] = settings.mfa_enabled
        user_data["mfa_default_method"] = settings.mfa_default_method

        # Use repository for atomic creation and invite code update
        try:
            db_user = await self.repo.create_with_invite(user_data, code)
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
            raise BusinessRuleViolation("errors.users.create_failed")

        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        return db_user

    @auditable(SecurityEvent.ADMIN_USER_CREATE)
    async def create_user(
        self,
        data: schemas.UserCreate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        """Admin create user."""
        if current_user.role != "admin":
            raise PermissionDenied()

        if data.invite_code:
            code_obj = await self.repo.get_invite_code(data.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite_code")
        elif data.role in ["teacher"]:
            raise BusinessRuleViolation("errors.users.invite_code_required")

        if await self.repo.check_email_exists(data.email):
            raise EntityAlreadyExists("User", data.email)

        password = data.password
        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(password)
        hashed = await get_password_hash(password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        user = await self.repo.create(user_data)

        await ensure_mfa_relationships_loaded(self.repo.db, user)
        await attach_pending_email(self.repo.db, user)
        return user

    async def upload_avatar(
        self,
        user: models.User,
        file: UploadFile,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "avatars", f"user_{user.id}_avatar")

        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        if db_user.profile:
            db_user.profile.avatar_url = file_url
        try:
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
            await delete_static_file(file_url)
            raise
        return db_user

    async def upload_cover(
        self,
        user: models.User,
        file: UploadFile,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "covers", f"user_{user.id}_cover")

        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        if db_user.profile:
            db_user.profile.cover_url = file_url
        try:
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
            await delete_static_file(file_url)
            raise
        return db_user
