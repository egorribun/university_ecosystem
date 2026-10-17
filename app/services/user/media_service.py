from types import TracebackType
from typing import Literal
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

import app.models as models
from app.core.exceptions.domain import EntityNotFound
from app.core.logging import get_logger
from app.core.protocols import UserLike, extract_user_id
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.dtos import UserDTO
from app.services.user.logic import (
    ProfileMediaKind,
    delete_owned_profile_media,
    update_user_attributes,
)

logger = get_logger(__name__)


async def save_upload(
    file: UploadFile,
    subdir: str,
    prefix: str,
    *,
    locale: str | None = None,
) -> str:
    """Load the optional image backend only when an upload is requested."""

    from app.api.utils import save_upload as _save_upload

    return await _save_upload(file, subdir, prefix, locale=locale)


async def delete_static_file(
    path: str, *, owner_id: UUID, media_kind: ProfileMediaKind
) -> None:
    """Delete profile media after validating its owner-scoped storage key."""

    await delete_owned_profile_media(path, owner_id=owner_id, media_kind=media_kind)


class UserMediaService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repo = uow.users

    async def _profile_media_is_referenced(self, file_url: str) -> bool:
        """Check both profile columns on the primary session; retain on uncertainty."""

        try:
            result = await self.repo.db.execute(
                select(models.UserProfile.user_id)
                .where(
                    or_(
                        models.UserProfile.avatar_url == file_url,
                        models.UserProfile.cover_url == file_url,
                    )
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None
        except (SQLAlchemyError, ConnectionError, OSError, TimeoutError, RuntimeError):
            logger.warning("profile_media_reference_check_failed")
            return True

    async def _cleanup_unreferenced_media(
        self,
        file_url: str | None,
        *,
        owner_id: UUID,
        media_kind: ProfileMediaKind,
    ) -> None:
        if not file_url or await self._profile_media_is_referenced(file_url):
            return
        await delete_static_file(file_url, owner_id=owner_id, media_kind=media_kind)

    async def _cleanup_after_commit(
        self,
        file_url: str | None,
        *,
        owner_id: UUID,
        media_kind: ProfileMediaKind,
    ) -> None:
        try:
            await self._cleanup_unreferenced_media(
                file_url, owner_id=owner_id, media_kind=media_kind
            )
        except (
            BotoCoreError,
            ClientError,
            ConnectionError,
            FileNotFoundError,
            OSError,
            TimeoutError,
            ValueError,
        ):
            # The database reference is already durable; a stale object can be swept later.
            logger.warning("profile_media_post_commit_cleanup_failed")

    async def cleanup_anonymized_profile_media(
        self,
        owner_id: UUID,
        *,
        avatar_url: str | None,
        cover_url: str | None,
    ) -> None:
        """Clean old profile objects after anonymization has committed."""
        await self._cleanup_after_commit(
            avatar_url, owner_id=owner_id, media_kind="avatar"
        )
        await self._cleanup_after_commit(
            cover_url, owner_id=owner_id, media_kind="cover"
        )

    async def _commit_profile_media_change(
        self,
        db_user: models.User,
        user_identity: UUID,
        *,
        field_name: Literal["avatar_url", "cover_url"],
        new_url: str | None,
        old_url: str | None,
        media_kind: ProfileMediaKind,
        cleanup_on_failure_url: str | None,
    ) -> None:
        failure: Exception | None = None
        failure_traceback: TracebackType | None = None
        try:
            async with self.uow:
                try:
                    update_user_attributes(db_user, {field_name: new_url})
                    self.repo.add(db_user)
                    await self.uow.commit()
                except Exception as exc:  # RZ-22-01-JUSTIFIED: cleanup before re-raise
                    failure = exc
                    failure_traceback = exc.__traceback__
                    rollback_succeeded = False
                    try:
                        await self.uow.rollback()
                        rollback_succeeded = True
                    except (
                        Exception
                    ):  # RZ-22-01-JUSTIFIED: preserve original if rollback fails
                        logger.warning("profile_media_rollback_failed")

                    if rollback_succeeded and cleanup_on_failure_url:
                        try:
                            await self._cleanup_unreferenced_media(
                                cleanup_on_failure_url,
                                owner_id=user_identity,
                                media_kind=media_kind,
                            )
                        except (
                            Exception
                        ):  # RZ-22-01-JUSTIFIED: preserve original if cleanup fails
                            logger.warning("profile_media_failure_cleanup_failed")
                else:
                    if old_url and old_url != new_url:
                        await self._cleanup_after_commit(
                            old_url, owner_id=user_identity, media_kind=media_kind
                        )
        except (
            Exception
        ):  # RZ-22-01-JUSTIFIED: preserve original if UoW exit cleanup fails
            if failure is None:
                raise
            logger.warning("profile_media_uow_exit_failed")

        if failure is not None:
            raise failure.with_traceback(failure_traceback)

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

        old_url = db_user.profile.avatar_url if db_user.profile else None
        file_url = await save_upload(file, "avatars", f"user_{user_identity}_avatar")
        await self._commit_profile_media_change(
            db_user,
            user_identity,
            field_name="avatar_url",
            new_url=file_url,
            old_url=old_url,
            media_kind="avatar",
            cleanup_on_failure_url=file_url,
        )
        return self.repo._to_dto(db_user)

    async def upload_cover(self, user: UserLike, file: UploadFile) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        old_url = db_user.profile.cover_url if db_user.profile else None
        file_url = await save_upload(file, "covers", f"user_{user_identity}_cover")
        await self._commit_profile_media_change(
            db_user,
            user_identity,
            field_name="cover_url",
            new_url=file_url,
            old_url=old_url,
            media_kind="cover",
            cleanup_on_failure_url=file_url,
        )
        return self.repo._to_dto(db_user)

    async def delete_avatar(self, user: UserLike) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        old_url = db_user.profile.avatar_url if db_user.profile else None
        await self._commit_profile_media_change(
            db_user,
            user_identity,
            field_name="avatar_url",
            new_url=None,
            old_url=old_url,
            media_kind="avatar",
            cleanup_on_failure_url=old_url,
        )
        return self.repo._to_dto(db_user)

    async def delete_cover(self, user: UserLike) -> UserDTO:
        user_identity = extract_user_id(user)
        db_user = await self.repo.get_orm_for_update_with_relations(user_identity)
        if not db_user:
            raise EntityNotFound("User", user_identity)

        old_url = db_user.profile.cover_url if db_user.profile else None
        await self._commit_profile_media_change(
            db_user,
            user_identity,
            field_name="cover_url",
            new_url=None,
            old_url=old_url,
            media_kind="cover",
            cleanup_on_failure_url=old_url,
        )
        return self.repo._to_dto(db_user)
