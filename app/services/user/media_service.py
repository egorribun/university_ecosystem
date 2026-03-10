import logging

from fastapi import UploadFile

from app.api.utils import save_upload
from app.core.exceptions.domain import EntityNotFound
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.dtos import UserDTO
from app.services.user.logic import update_user_attributes
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserMediaService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repo = uow.users

    async def upload_avatar(self, user: UserDTO, file: UploadFile) -> UserDTO:
        db_user = await self.repo._get_orm(user.id, with_for_update=True)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "avatars", f"user_{user.id}_avatar")

        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        try:
            # Apply nested update via domain logic
            update_user_attributes(db_user, {"avatar_url": file_url})
            self.repo.add(db_user)
            async with self.uow:
                await self.uow.commit()
            return self.repo._to_dto(db_user)
        except Exception:
            await self.uow.rollback()
            await delete_static_file(file_url)
            raise

    async def upload_cover(self, user: UserDTO, file: UploadFile) -> UserDTO:
        db_user = await self.repo._get_orm(user.id, with_for_update=True)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "covers", f"user_{user.id}_cover")

        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        try:
            # Apply nested update via domain logic
            update_user_attributes(db_user, {"cover_url": file_url})
            self.repo.add(db_user)
            async with self.uow:
                await self.uow.commit()
            return self.repo._to_dto(db_user)
        except Exception:
            await self.uow.rollback()
            await delete_static_file(file_url)
            raise

    async def delete_avatar(self, user: UserDTO) -> UserDTO:
        db_user = await self.repo._get_orm(user.id, with_for_update=True)
        if not db_user:
            raise EntityNotFound("User", user.id)
        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        # Apply nested update via domain logic
        update_user_attributes(db_user, {"avatar_url": None})
        self.repo.add(db_user)
        async with self.uow:
            await self.uow.commit()
        return self.repo._to_dto(db_user)

    async def delete_cover(self, user: UserDTO) -> UserDTO:
        db_user = await self.repo._get_orm(user.id, with_for_update=True)
        if not db_user:
            raise EntityNotFound("User", user.id)
        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        # Apply nested update via domain logic
        update_user_attributes(db_user, {"cover_url": None})
        self.repo.add(db_user)
        async with self.uow:
            await self.uow.commit()
        return self.repo._to_dto(db_user)
