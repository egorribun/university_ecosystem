import logging

from fastapi import UploadFile

from app.api.utils import save_upload
from app.core.exceptions.domain import EntityNotFound
from app.repositories.user_repository import UserRepository
from app.schemas.dtos import UserDTO
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)

class UserMediaService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.repo = user_repo

    async def upload_avatar(self, user: UserDTO, file: UploadFile) -> UserDTO:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "avatars", f"user_{user.id}_avatar")

        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        try:
            updated_user = await self.repo.update(user.id, {"avatar_url": file_url})
            assert updated_user is not None
            await self.repo.commit()
            return updated_user
        except Exception:
            await self.repo.rollback()
            await delete_static_file(file_url)
            raise

    async def upload_cover(self, user: UserDTO, file: UploadFile) -> UserDTO:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "covers", f"user_{user.id}_cover")

        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        try:
            updated_user = await self.repo.update(user.id, {"cover_url": file_url})
            assert updated_user is not None
            await self.repo.commit()
            return updated_user
        except Exception:
            await self.repo.rollback()
            await delete_static_file(file_url)
            raise

    async def delete_avatar(self, user: UserDTO) -> UserDTO:
        db_user = await self.repo.get(user.id)
        assert db_user is not None
        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        updated_user = await self.repo.update(user.id, {"avatar_url": None})
        assert updated_user is not None
        await self.repo.commit()
        return updated_user

    async def delete_cover(self, user: UserDTO) -> UserDTO:
        db_user = await self.repo.get(user.id)
        assert db_user is not None
        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        updated_user = await self.repo.update(user.id, {"cover_url": None})
        assert updated_user is not None
        await self.repo.commit()
        return updated_user
