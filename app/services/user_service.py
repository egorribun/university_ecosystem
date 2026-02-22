import logging
import uuid

from fastapi import Request, UploadFile

# Re-exports for backward compatibility with existing tests
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService

logger = logging.getLogger(__name__)


class UserService:
    """
    Facade for user operations to maintain backward compatibility
    with existing routers and dependency injection, addressing the God Object pattern.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.repo = user_repo
        self.audit = audit
        self.notifications = notifications

        self.profile_service = UserProfileService(user_repo, audit, notifications)
        self.media_service = UserMediaService(user_repo)
        self.compliance_service = UserComplianceService(user_repo, audit)

    async def get_user_by_id(self, user_id: uuid.UUID | str) -> UserDTO | None:
        return await self.profile_service.get_user_by_id(user_id)

    async def get_user_by_email(self, email: str) -> UserDTO | None:
        return await self.profile_service.get_user_by_email(email)

    async def get_auth_user_by_email(self, email: str) -> UserAuthDTO | None:
        return await self.profile_service.get_auth_user_by_email(email)

    async def get_auth_user_by_id(self, user_id: uuid.UUID | str) -> UserAuthDTO | None:
        return await self.profile_service.get_auth_user_by_id(user_id)

    async def update_user_profile(
        self,
        user: UserDTO,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> UserDTO:
        return await self.profile_service.update_user_profile(user, data, request)

    async def get_users(
        self,
        request: Request,
        current_user: UserDTO | None = None,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[UserDTO]:
        return await self.profile_service.get_users(request, current_user, filters)

    async def admin_update_user(
        self,
        user_id: uuid.UUID | str,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: UserDTO,
    ) -> UserDTO:
        return await self.profile_service.admin_update_user(
            user_id, data, request, current_user
        )

    async def admin_delete_user(
        self,
        user_id: uuid.UUID | str,
        request: Request,
        current_user: UserDTO,
    ) -> dict:
        return await self.compliance_service.admin_delete_user(
            user_id, request, current_user
        )

    async def delete_avatar(self, user: UserDTO) -> UserDTO:
        return await self.media_service.delete_avatar(user)

    async def delete_cover(self, user: UserDTO) -> UserDTO:
        return await self.media_service.delete_cover(user)

    async def export_user_data(
        self, user: UserDTO, request: Request
    ) -> schemas.DataExportOut:
        return await self.compliance_service.export_user_data(user, request)

    async def delete_user_data(
        self, user: UserDTO, request: Request, *, confirm: bool
    ) -> schemas.DataDeletionOut:
        return await self.compliance_service.delete_user_data(
            user, request, confirm=confirm
        )

    async def register_user(self, user_in: schemas.UserCreate) -> UserDTO:
        return await self.compliance_service.register_user(user_in)

    async def create_user(
        self, data: schemas.UserCreate, request: Request, current_user: UserDTO
    ) -> UserDTO:
        return await self.compliance_service.create_user(data, request, current_user)

    async def upload_avatar(
        self, user: UserDTO, file: UploadFile
    ) -> UserDTO:
        return await self.media_service.upload_avatar(user, file)

    async def upload_cover(
        self, user: UserDTO, file: UploadFile
    ) -> UserDTO:
        return await self.media_service.upload_cover(user, file)
