from fastapi import UploadFile

from app.api.utils import save_upload
from app.core.exceptions.domain import EntityNotFound
from app.core.logging import get_logger
from app.core.protocols import UserLike, extract_user_id
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.dtos import UserDTO
from app.services.user.logic import update_user_attributes
from app.utils.files import delete_static_file

logger = get_logger(__name__)


class UserMediaService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repo = uow.users

    async def upload_avatar(self, user: UserLike, file: UploadFile) -> UserDTO:
        user_identity = extract_user_id(user)
        # Fetch the row-locked ORM user WITH profile/preferences/education_path
        # eager-loaded. Required because update_user_attributes() below mutates
        # the profile, and `db_user.profile` is lazy="noload" — a bare _get_orm()
        # reads it as None, so the old-avatar cleanup is skipped AND a duplicate
        # UserProfile is INSERTed -> UNIQUE violation (the W185 noload twin-bug).
        # _to_dto() remains the one private call pending a public to_dto().
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        file_url = await save_upload(file, "avatars", f"user_{user_identity}_avatar")

        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        try:
            # Apply nested update via domain logic
            update_user_attributes(db_user, {"avatar_url": file_url})
            self.repo.add(db_user)
            async with self.uow:
                await self.uow.commit()
            return self.repo._to_dto(db_user)
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback and cleanup file then re-raise (reviewed TD-27-04)
            await self.uow.rollback()
            await delete_static_file(file_url)
            raise

    async def upload_cover(self, user: UserLike, file: UploadFile) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        file_url = await save_upload(file, "covers", f"user_{user_identity}_cover")

        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        try:
            # Apply nested update via domain logic
            update_user_attributes(db_user, {"cover_url": file_url})
            self.repo.add(db_user)
            async with self.uow:
                await self.uow.commit()
            return self.repo._to_dto(db_user)
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback and cleanup file then re-raise (reviewed TD-27-04)
            await self.uow.rollback()
            await delete_static_file(file_url)
            raise

    async def delete_avatar(self, user: UserLike) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)
        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        # Apply nested update via domain logic
        update_user_attributes(db_user, {"avatar_url": None})
        self.repo.add(db_user)
        async with self.uow:
            await self.uow.commit()
        return self.repo._to_dto(db_user)

    async def delete_cover(self, user: UserLike) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)
        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        # Apply nested update via domain logic
        update_user_attributes(db_user, {"cover_url": None})
        self.repo.add(db_user)
        async with self.uow:
            await self.uow.commit()
        return self.repo._to_dto(db_user)
