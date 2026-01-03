"""
User repository for user data access operations.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
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
            select(User).where(func.lower(User.email) == normalized)
        )
        return result.scalars().first()

    async def get_by_email_or_raise(self, email: str) -> User:
        """Get user by email or raise ValueError."""
        user = await self.get_by_email(email)
        if user is None:
            raise ValueError(f"User with email {email} not found")
        return user

    async def get_active_users(self, *, skip: int = 0, limit: int = 100) -> list[User]:
        """Get only active users."""
        result = await self.db.execute(
            select(User).where(User.is_active.is_(True)).offset(skip).limit(limit)
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
        )
        return list(result.scalars().all())


def get_user_repository(db: AsyncSession) -> UserRepository:
    """Factory function for dependency injection."""
    return UserRepository(db)


__all__ = ["UserRepository", "get_user_repository"]
