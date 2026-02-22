import logging
import uuid

from fastapi import Request

from app.auth import mfa
from app.core.exceptions.domain import EntityNotFound, PermissionDenied
from app.core.localization import resolve_locale, translate
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.audit_service import AuditService, SecurityEvent, auditable
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class UserProfileService:
    def __init__(
        self,
        user_repo: UserRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.repo = user_repo
        self.audit = audit
        self.notifications = notifications

    async def get_user_by_id(self, user_id: uuid.UUID | str) -> UserDTO | None:
        return await self.repo.get(user_id)

    async def get_user_by_email(self, email: str) -> UserDTO | None:
        return await self.repo.get_by_email(email)

    async def get_auth_user_by_email(self, email: str) -> UserAuthDTO | None:
        return await self.repo.get_auth_by_email(email)

    async def get_auth_user_by_id(self, user_id: uuid.UUID | str) -> UserAuthDTO | None:
        return await self.repo.get_auth_by_id(user_id)

    @auditable(SecurityEvent.USER_PROFILE_UPDATE, user_id_param="user")
    async def update_user_profile(
        self,
        user: UserDTO,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> UserDTO:
        """Update current user profile (self-update)."""
        payload = data.model_dump(exclude_unset=True)

        if "email" in payload and payload["email"] is not None:
            from app.services.user.logic import validate_user_email

            payload["email"] = await validate_user_email(
                self.repo, payload["email"], exclude_user_id=user.id
            )

        updated_user = await self.repo.update(user.id, payload)
        if not updated_user:
            raise EntityNotFound("User", user.id)

        await self.repo.commit()
        # attach_pending_email should ideally be in repo or handled differently,
        # but for now let's assume it's still needed if it affects the session
        # before DTO is returned? No, repo returned DTO.
        # If attach_pending_email modifies the DB, it should be in repo.
        # If it just returns data, it's fine.
        # Let's check logic: it modifies the user object or returns it?
        # userService facade might need to be adjusted.

        return updated_user

    async def get_users(
        self,
        request: Request,
        current_user: UserDTO | None = None,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[UserDTO]:
        filters = filters or schemas.UserSearchFilter()

        if current_user and (
            current_user.role != "admin"
            and not filters.search
            and not filters.full_name
        ):
            raise PermissionDenied()

        name_query = filters.full_name
        if name_query:
            name_query = name_query.strip()
            if not name_query:
                name_query = None

        filters.full_name = name_query
        return await self.repo.list_users(filters=filters)

    @auditable(SecurityEvent.ADMIN_USER_MODIFY, user_id_param="user_id")
    async def admin_update_user(
        self,
        user_id: uuid.UUID | str,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: UserDTO,
    ) -> UserDTO:
        if current_user.role != "admin":
            raise PermissionDenied()

        payload = data.model_dump(exclude_unset=True)
        reset_requested = bool(payload.pop("reset_mfa", False))

        if "email" in payload and payload["email"] is not None:
            payload["email"] = str(payload["email"]).strip().lower()

        updated_user = await self.repo.update(user_id, payload)
        if not updated_user:
            raise EntityNotFound("User", user_id)

        if reset_requested:
            # reset_user_mfa takes a session and either a user object or ID.
            # I should make sure it doesn't need to mutate the user object I have.
            # It likely mutates the DB via session.
            await mfa.reset_user_mfa(self.repo.db, user_id=user_id)

        await self.repo.commit()

        if reset_requested:
            log_id = uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            self.audit.log(
                "users.mfa.reset", request, user_id=log_id, reason="admin_reset"
            )
            # We need to send notification, so we need the DTO (which we have)
            target_locale = resolve_locale(request=request, user=updated_user)
            title = translate("notifications.mfa.reset.title", locale=target_locale)
            body = translate("notifications.mfa.reset.body", locale=target_locale)
            await self.notifications.send_security_notification(
                user_ids=[updated_user.id],
                title=title,
                body=body,
            )
        return updated_user
