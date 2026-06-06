from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from fastapi import Request

from app.auth import mfa
from app.core.exceptions.domain import EntityNotFound, PermissionDenied
from app.core.localization import resolve_locale, translate
from app.core.logging import get_logger
from app.core.protocols import UserLike, extract_user_id
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.audit_service import AuditService, SecurityEvent, auditable
from app.services.auth_service import attach_pending_email
from app.services.notification_service import NotificationService
from app.services.user.logic import update_user_attributes

if TYPE_CHECKING:
    from app.models import User

logger = get_logger(__name__)


class UserProfileService:
    def __init__(
        self,
        uow: UnitOfWork,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.uow = uow
        self.repo = uow.users
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
        user: UserLike,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> UserDTO:
        """Update current user profile (self-update)."""
        payload = data.model_dump(exclude_unset=True)

        if "email" in payload and payload["email"] is not None:
            from app.services.user.logic import validate_user_email

            user_identity = extract_user_id(user)
            payload["email"] = await validate_user_email(
                self.repo, payload["email"], exclude_user_id=user_identity
            )

        # Fetch ORM user WITH child relations eager-loaded + row-locked. The
        # eager-load is required: update_user_attributes() decides INSERT-vs-
        # UPDATE on profile/preferences/education_path via `if not user.<child>`,
        # but those relationships are lazy="noload" so a bare _get_orm() reads
        # them as None even when a row exists -> duplicate INSERT -> UNIQUE
        # violation (the W185 noload twin-bug).
        # Handle UserLike (could be ID, DTO or ORM)
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        # Apply nested updates
        update_user_attributes(db_user, payload)

        self.repo.add(db_user)
        async with self.uow:
            await self.uow.commit()

        # Convert back to DTO
        updated_user = self.repo._to_dto(db_user)
        # Attach pending email if any
        updated_user = cast(
            UserDTO, await attach_pending_email(self.repo.db, updated_user)
        )

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
        current_user: UserDTO | User,
    ) -> UserDTO:
        if current_user.role != "admin":
            raise PermissionDenied()

        payload = data.model_dump(exclude_unset=True)
        reset_requested = bool(payload.pop("reset_mfa", False))

        if "email" in payload and payload["email"] is not None:
            payload["email"] = str(payload["email"]).strip().lower()

        # Fetch ORM user WITH child relations eager-loaded + row-locked
        # (noload twin-bug — see update_user_profile above).
        db_user = await self.repo.get_orm_for_update_with_relations(user_id)
        if not db_user:
            raise EntityNotFound("User", user_id)

        # Apply nested updates
        update_user_attributes(db_user, payload)

        self.repo.add(db_user)
        await self.uow.flush()
        updated_user = self.repo._to_dto(db_user)

        if reset_requested:
            # reset_user_mfa takes a session and either a user object or ID.
            # I should make sure it doesn't need to mutate the user object I have.
            # It likely mutates the DB via session.
            await mfa.reset_user_mfa(self.repo.db, user_id=user_id)

        async with self.uow:
            await self.uow.commit()

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
