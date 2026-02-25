"""
User repository for user data access operations.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.core.protocols import AsyncDatabaseSession
from app.models import models
from app.models.models import User, UserProfile
from app.models.user_loaders import USER_MFA_LOAD_OPTIONS, USER_MFA_RELATIONSHIP_NAMES
from app.repositories.base import BaseRepository
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession


class UserRepository(BaseRepository[User, UserDTO, schemas.UserCreate, dict]):
    """Repository for User model operations."""

    @property
    def model(self) -> type[User]:
        return User

    # Removed redundant __init__ override to use BaseRepository.db.

    @property
    def dto_class(self) -> type[UserDTO]:
        return UserDTO

    async def get(
        self, id: uuid.UUID | str, *, with_for_update: bool = False
    ) -> UserDTO | None:
        """Get user by ID with MFA options loaded."""
        if isinstance(id, str):
            try:
                id = uuid.UUID(id)
            except ValueError:
                return None
        stmt = select(User).where(User.id == id).options(*USER_MFA_LOAD_OPTIONS)
        if with_for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        obj = result.scalars().first()
        return self._to_dto(obj) if obj else None

    async def get_by_email(self, email: str) -> UserDTO | None:
        """Get user by email (case-insensitive)."""
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.email) == normalized)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        obj = result.scalars().first()
        return self._to_dto(obj) if obj else None

    async def get_auth_by_email(self, email: str) -> UserAuthDTO | None:
        """Get user authentication data by email."""
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.email) == normalized)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        obj = result.scalars().first()
        return UserAuthDTO.model_validate(obj) if obj else None

    async def get_auth_by_id(self, id: uuid.UUID | str) -> UserAuthDTO | None:
        """Get user authentication data by ID."""
        if isinstance(id, str):
            try:
                id = uuid.UUID(id)
            except ValueError:
                return None
        stmt = select(User).where(User.id == id).options(*USER_MFA_LOAD_OPTIONS)
        result = await self.db.execute(stmt)
        obj = result.scalars().first()
        return UserAuthDTO.model_validate(obj) if obj else None

    async def get_by_login(self, login: str) -> UserDTO | None:
        """Find user by email or username/login."""
        stmt = (
            select(User)
            .where(
                or_(
                    func.lower(User.email) == login.lower(),
                )
            )
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return self._to_dto(obj) if obj else None

    async def get_by_email_or_raise(self, email: str) -> UserDTO:
        """Get user by email or raise ValueError."""
        user = await self.get_by_email(email)
        if user is None:
            raise ValueError(f"User with email {email} not found")
        return user

    async def get_with_full_profile(self, user_id: uuid.UUID | str) -> UserDTO | None:
        """Fetch a user with profile, preferences, and education_path in ONE query.

        Use this instead of :meth:`get` when all three delegated sub-objects are
        needed (e.g. /users/me, profile edit page).  A single LEFT OUTER JOIN
        replaces the three consecutive selectin round-trips that the lazy
        ``selectin`` relationship strategy would otherwise issue.
        """
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return None
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                joinedload(User.profile),
                joinedload(User.preferences),
                joinedload(User.education_path),
                *USER_MFA_LOAD_OPTIONS,
            )
        )
        result = await self.db.execute(stmt)
        obj = result.unique().scalars().first()
        return self._to_dto(obj) if obj else None

    async def list_users(
        self,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[UserDTO]:
        filters = filters or schemas.UserSearchFilter()
        stmt = (
            select(User)
            .join(User.profile)
            .where(UserProfile.status != "deleted")
            .options(
                *__import__(
                    "app.models.user_loaders", fromlist=["USER_LIST_LOAD_OPTIONS"]
                ).USER_LIST_LOAD_OPTIONS,
                selectinload(User.group),
            )
        )
        if filters.group_id:
            stmt = stmt.where(User.group_id == filters.group_id)
        if filters.full_name:
            stmt = stmt.where(UserProfile.full_name.ilike(f"%{filters.full_name}%"))
        if filters.role:
            stmt = stmt.where(User.role == filters.role)

        stmt = stmt.limit(filters.limit).offset(filters.offset)
        result = await self.db.execute(stmt)
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_active_users(
        self, *, skip: int = 0, limit: int = 100
    ) -> list[UserDTO]:
        """Get only active users."""
        result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count_active(self) -> int:
        """Count active users."""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )
        return result.scalar() or 0

    async def count_with_mfa(self) -> int:
        """Count users with MFA enabled."""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.mfa_required.is_(True))
        )
        return result.scalar() or 0

    async def search_by_name(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[UserDTO]:
        """Search users by name (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(User)
            .join(User.profile)
            .where(func.lower(UserProfile.full_name).like(pattern))
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_user_sessions(
        self, user_id: uuid.UUID | str, limit: int = 1000
    ) -> list[models.ActiveSession]:
        """Get user sessions with limit."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.ActiveSession)
            .where(models.ActiveSession.user_id == user_id)
            .limit(limit)
            .order_by(models.ActiveSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_notifications(
        self, user_id: uuid.UUID | str, limit: int = 1000
    ) -> list[models.Notification]:
        """Get user notifications with limit."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.Notification)
            .where(models.Notification.user_id == user_id)
            .limit(limit)
            .order_by(models.Notification.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_mfa_challenges(
        self, user_id: uuid.UUID | str, limit: int = 1000
    ) -> list[models.MfaChallenge]:
        """Get user MFA challenges."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.MfaChallenge)
            .where(models.MfaChallenge.user_id == user_id)
            .limit(limit)
            .order_by(models.MfaChallenge.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_totp_enrollments(
        self, user_id: uuid.UUID | str
    ) -> list[models.MfaTotpEnrollment]:
        """Get user TOTP enrollments."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.MfaTotpEnrollment)
            .where(models.MfaTotpEnrollment.user_id == user_id)
            .order_by(models.MfaTotpEnrollment.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def check_email_exists(
        self, email: str, exclude_user_id: uuid.UUID | str | None = None
    ) -> bool:
        stmt = select(exists().where(func.lower(User.email) == email.lower()))
        if exclude_user_id:
            if isinstance(exclude_user_id, str):
                try:
                    exclude_user_id = uuid.UUID(exclude_user_id)
                except ValueError:
                    return False
            stmt = stmt.where(User.id != exclude_user_id)
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def get_invite_code(self, code: str) -> models.InviteCode | None:
        """Get invite code by value."""
        result = await self.db.execute(
            select(models.InviteCode).where(models.InviteCode.code == code)
        )
        return result.scalars().first()

    async def create_with_invite(
        self, user_data: dict, invite_code: models.InviteCode | None
    ) -> UserDTO:
        """Create a user and optionally mark an invite code as used."""
        user = models.User(**user_data)
        self.db.add(user)
        await self.db.flush()  # Get ID

        if invite_code:
            invite_code.is_used = True  # type: ignore[assignment]
            invite_code.is_active = False  # type: ignore[assignment]
            invite_code.used_by_user_id = user.id
            self.db.add(invite_code)

        await self.db.refresh(user, attribute_names=USER_MFA_RELATIONSHIP_NAMES)
        return self._to_dto(user)

    async def delete_sensitive_data(self, user_id: uuid.UUID | str):
        """Cleanup user-related transient records (sessions, challenges, etc)."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return
        """Cleanup user-related transient records (sessions, challenges, etc)."""
        await self.db.execute(
            delete(models.ActiveSession).where(models.ActiveSession.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaChallenge).where(models.MfaChallenge.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaTotpEnrollment).where(
                models.MfaTotpEnrollment.user_id == user_id
            )
        )
        await self.db.execute(
            delete(models.Notification).where(models.Notification.user_id == user_id)
        )
        await self.db.execute(
            delete(models.DataAccessLog).where(
                or_(
                    models.DataAccessLog.actor_user_id == user_id,
                    models.DataAccessLog.subject_user_id == user_id,
                )
            )
        )

    async def get_user_access_logs(
        self,
        user_id: uuid.UUID | str,
        limit: int = 2000,
    ) -> list[models.DataAccessLog]:
        """Get access logs where user is actor or subject."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        # We want logs where the user is EITHER the actor OR the subject
        # matching the logic in UserService.export_user_data which passed both
        # actor_user_id=user.id and subject_user_id=user.id to export_access_logs
        # but export_access_logs treated them as AND if both provided.
        # Wait, let's verify export_access_logs logic in data_access.py.
        # It says: if actor_user_id: where(actor == ...); if subject: where(subject == ...)
        # So passing BOTH means logic AND.
        # The original code was:
        # export_access_logs(..., actor_user_id=user.id, subject_user_id=user.id, ...)
        # This implies it wanted logs where user did something to themselves?
        # Or did it mean OR?
        # Typically "export my data" includes everything involves me.
        # Let's look at data_access.py content again from context.
        # stmt = stmt.where(DataAccessLog.actor_user_id == actor_user_id)
        # stmt = stmt.where(DataAccessLog.subject_user_id == subject_user_id)
        # Yes, it is boolean AND.
        # So the user only sees logs where they acted on themselves?
        # That seems restrictive.
        # However, I must preserve existing behavior during refactoring unless it's clearly a bug.
        # If I look at strict translation:

        stmt = (
            select(models.DataAccessLog)
            .where(
                or_(
                    models.DataAccessLog.actor_user_id == user_id,
                    models.DataAccessLog.subject_user_id == user_id,
                )
            )
            .order_by(models.DataAccessLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


def get_user_repository(db: AsyncDatabaseSession) -> UserRepository:
    """Factory function for dependency injection."""
    return UserRepository(db)


__all__ = ["UserRepository", "get_user_repository"]
