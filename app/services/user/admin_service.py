import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
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
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.notification_service import NotificationService
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserAdminService:
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

        # Update fields
        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}

        for field, value in payload.items():
            if field in preferences_fields:
                if not db_user.preferences:
                    db_user.preferences = models.UserPreferences(user_id=db_user.id)
                setattr(db_user.preferences, field, value)
            else:
                setattr(db_user, field, value)

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
        if reset_stats is not None and reset_stats.changed:
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
        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.repo.get(user_id)
        if db_user is None:
            raise EntityNotFound("User", user_id)

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

        await self.repo.delete_sensitive_data(user_id)

        db_user.preferences = None
        db_user.spotify = None

        self.audit.log(
            "users.admin_delete", request, user_id=user_id, reason="admin_delete"
        )

        await self.db.commit()
        return {"deleted": True, "user_id": user_id}

    async def create_user(
        self,
        data: schemas.UserCreate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
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
        hashed = get_password_hash(password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        user = await self.repo.create(user_data)

        self.audit.log("users.create", request, user_id=user.id, reason="admin_create")
        await ensure_mfa_relationships_loaded(self.db, user)
        await attach_pending_email(self.db, user)
        return user
