import logging
from typing import TYPE_CHECKING

from fastapi import Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import save_upload
from app.core.exceptions.domain import EntityNotFound
from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.auth_service import attach_pending_email
from app.utils.files import delete_static_file

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class UserProfileService:
    def __init__(
        self,
        db: AsyncSession,
        repo: UserRepository,
    ) -> None:
        self.db = db
        self.repo = repo

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
                from app.core.exceptions.domain import EntityAlreadyExists

                raise EntityAlreadyExists("User", validated_email)
            update_fields["email"] = validated_email

        from app.services.user.logic import update_user_attributes

        update_user_attributes(db_user, update_fields)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)
        return db_user

    async def delete_avatar(self, user: models.User) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)
        db_user.avatar_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def delete_cover(self, user: models.User) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)
        db_user.cover_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

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
