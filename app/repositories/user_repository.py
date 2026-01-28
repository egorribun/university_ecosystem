"""
User repository for user data access operations.
"""

from __future__ import annotations

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import models
from app.models.models import User
from app.models.user_loaders import USER_MFA_LOAD_OPTIONS
from app.repositories.base import BaseRepository
from app.schemas.schemas import UserCreate


class UserRepository(BaseRepository[User, UserCreate, dict]):
    """Repository for User model operations."""

    @property
    def model(self) -> type[User]:
        return User

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email (case-insensitive)."""
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.email) == normalized)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        return result.scalars().first()

    async def get_by_login(self, login: str) -> User | None:
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
        return result.scalar_one_or_none()

    async def get_by_email_or_raise(self, email: str) -> User:
        """Get user by email or raise ValueError."""
        user = await self.get_by_email(email)
        if user is None:
            raise ValueError(f"User with email {email} not found")
        return user

    async def list_users(
        self,
        *,
        group_id: int | None = None,
        full_name: str | None = None,
        role: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        stmt = (
            select(User)
            .where(User.status != "deleted")
            .options(*USER_MFA_LOAD_OPTIONS, selectinload(User.group))
        )
        if group_id:
            stmt = stmt.where(User.group_id == group_id)
        if full_name:
            stmt = stmt.where(User.full_name.ilike(f"%{full_name}%"))
        if role:
            stmt = stmt.where(User.role == role)

        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_users(self, *, skip: int = 0, limit: int = 100) -> list[User]:
        """Get only active users."""
        result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        return list(result.scalars().all())

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
    ) -> list[User]:
        """Search users by name (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.full_name).like(pattern))
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        return list(result.scalars().all())

    async def check_email_exists(
        self, email: str, exclude_user_id: int | None = None
    ) -> bool:
        stmt = select(exists().where(func.lower(User.email) == email.lower()))
        if exclude_user_id:
            stmt = stmt.where(User.id != exclude_user_id)
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def delete_sensitive_data(self, user_id: int):
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


def get_user_repository(db: AsyncSession) -> UserRepository:
    """Factory function for dependency injection."""
    return UserRepository(db)


__all__ = ["UserRepository", "get_user_repository"]
