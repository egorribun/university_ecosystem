import logging
from typing import Any

from fastapi import Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import save_upload
from app.auth.security import get_password_hash
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.deps.cache import BaseCache
from app.models import models
from app.models.user_loaders import (
    ensure_mfa_relationships_loaded,
)
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.data_access import export_access_logs, log_data_access
from app.services.notification_service import NotificationService
from app.services.user.logic import anonymize_user_data, update_user_attributes
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    async def get_user_by_email(self, email: str) -> models.User | None:
        """Get user by email."""
        return await self.repo.get_by_email(email)

    def __init__(
        self,
        db: AsyncSession,
        repo: UserRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.notifications = notifications

    async def update_user_profile(
        self,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        update_fields = data.model_dump(exclude_unset=True)

        if "email" in update_fields and update_fields["email"] is not None:
            validated_email = str(update_fields["email"]).strip().lower()
            if await self.repo.check_email_exists(
                validated_email, exclude_user_id=user.id
            ):
                raise EntityAlreadyExists("User", validated_email)
            update_fields["email"] = validated_email

        # ... (keeping complex mapping logic in service for now as it's business-heavy)

        update_user_attributes(db_user, update_fields)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)
        return db_user

    async def get_users(
        self,
        request: Request,
        current_user: models.User,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[models.User]:
        filters = filters or schemas.UserSearchFilter()
        if (
            current_user.role != "admin"
            and not filters.search
            and not filters.full_name
        ):
            raise PermissionDenied()

        name_query = filters.search if filters.search else filters.full_name
        # We update filters with the name query for repository call
        filters.full_name = name_query
        return await self.repo.list_users(filters=filters)

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
            from app.auth import mfa

            reset_stats = await mfa.reset_user_mfa(self.db, user=db_user)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)

        updated_user = db_user

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
                await self.notifications.send_security_notification(
                    user_ids=[updated_user.id],
                    title=title,
                    body=body,
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

        db_user = await self.repo.get(user_id)
        if db_user is None:
            raise EntityNotFound("User", user_id)

        # Prevent admin from deleting themselves
        if db_user.id == current_user.id:
            raise BusinessRuleViolation("errors.users.cannot_delete_self")

        await anonymize_user_data(db_user)

        self.audit.log(
            "users.admin_delete", request, user_id=user_id, reason="admin_delete"
        )

        await self.db.commit()
        return {"deleted": True, "user_id": user_id}

    async def delete_avatar(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
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
        db_user = await self.repo.get(user.id)
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
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
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

        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(user.id)

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
        return schemas.DataDeletionOut(deleted=True, anonymized_email=db_user.email)

    async def register_user(
        self,
        user_in: schemas.UserCreate,
    ) -> models.User:
        """Register a new user (public signup)."""
        raw_role = getattr(user_in, "role", None)
        # Import UserRole if not present or use string
        from app.core.config import settings
        from app.models.enums import UserRole

        requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT
        normalized_email = user_in.email.strip().lower()

        if await self.repo.check_email_exists(normalized_email):
            raise EntityAlreadyExists("User", normalized_email)

        code = None
        if hasattr(user_in, "invite_code") and requested_role in (
            UserRole.TEACHER,
            UserRole.ADMIN,
        ):
            # We fetch the code and validate it manually to keep repo simple
            # or we could make a specific repo method `get_valid_invite_code`.
            # Let's use get_invite_code and validate.
            code_obj = await self.repo.get_invite_code(user_in.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite")

            # Validation logic from crud
            if (
                code_obj.role != requested_role.value
                or not code_obj.is_active
                or code_obj.is_used
            ):
                raise BusinessRuleViolation("errors.users.invalid_invite")
            code = code_obj

        hashed_password = get_password_hash(user_in.password)

        # Mapping logic
        user_data = user_in.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed_password
        user_data["role"] = requested_role.value
        user_data["email"] = normalized_email
        if "id" in user_data:
            del user_data["id"]

        # Default fields from crud
        user_data["mfa_required"] = settings.mfa_enabled
        user_data["mfa_default_method"] = settings.mfa_default_method

        # Handle nested fields if schema has them flat?
        # Crud used manual mapping.
        # Let's use repo.create for simplicity but we might need to handle
        # specific fields if schemas.UserCreate is flat but model is not.
        # schemas.UserCreate seems flat.
        # But crud logic (lines 80-102) maps many fields explicitly.
        # Most match, but some are nested in model (preferences, profile_detail)?
        # No, User model has these fields directly (department, position, etc.)
        # except where they were moved to mixins or separate tables?
        # Crud lines 86-99 seem to map attributes directly to User model.
        # So repo.create(**user_data) should work if user_data keys match User columns.

        # However, crud explicitly sets `mfa_required`.
        # And creates User object directly.
        # Let's use repo.create to be consistent with Repository pattern.
        # But we need to update the invite code transactionally.

        # We can do:
        # user = await self.repo.create(user_data) -> does commit
        # Then update code -> does commit
        # But ideally all in one transaction.
        # Repo.create does commit/refresh.

        # If we use repo.create, we can't wrap it easily in a larger tx
        # unless we modify repo to accept commit=False.
        # Or we use a Unit of Work.
        # For now, let's accept slight risk or modify repo to not auto-commit?
        # BaseRepository `create` calls `db.commit()`.

        # Let's assume we can live with separate commits for now
        # (User created, then Code marked used).
        # Worst case: User created, code not marked. User is valid, code reusable.
        # Risk: Code reusable.
        # Mitigation: Update code first? No, need user_id.

        # Solution: Use `self.db` directly here for transactionality?
        # Or use `repo.db`.

        from sqlalchemy.exc import IntegrityError

        # Let's do manuals:
        db_user = models.User(**user_data)
        self.db.add(db_user)

        if code:
            code.is_used = True
            code.is_active = False
            self.db.add(code)

        try:
            await self.db.flush()  # to get ID
            if code:
                code.used_by_user_id = db_user.id
            await self.db.commit()
            await self.db.refresh(db_user)
        except IntegrityError as exc:
            await self.db.rollback()
            error_str = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "email" in error_str or "users_email_key" in error_str:
                raise EntityAlreadyExists("User", normalized_email)
            raise BusinessRuleViolation("errors.users.create_failed")
        except Exception:
            await self.db.rollback()
            raise BusinessRuleViolation("errors.users.create_failed")

        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

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
            # Logic from before
            raise BusinessRuleViolation("errors.users.invite_code_required")

        password = data.password
        hashed = get_password_hash(password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        from sqlalchemy.exc import IntegrityError
        try:
            # Use repo.create
            user = await self.repo.create(user_data)
        except IntegrityError as exc:
            await self.db.rollback()
            error_str = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "email" in error_str or "users_email_key" in error_str:
                raise EntityAlreadyExists("User", data.email)
            raise BusinessRuleViolation("errors.users.create_failed")

        self.audit.log("users.create", request, user_id=user.id, reason="admin_create")
        await ensure_mfa_relationships_loaded(self.db, user)
        await attach_pending_email(self.db, user)
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

        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)

        db_user.avatar_url = file_url
        try:
            await self.db.commit()
            await self.db.refresh(db_user)
        except Exception:
            await self.db.rollback()
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

        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)

        db_user.cover_url = file_url
        try:
            await self.db.commit()
            await self.db.refresh(db_user)
        except Exception:
            await self.db.rollback()
            await delete_static_file(file_url)
            raise
        return db_user

