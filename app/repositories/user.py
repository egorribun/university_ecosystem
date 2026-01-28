from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.models import models
from app.models.user_loaders import USER_MFA_LOAD_OPTIONS
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[models.User]):
    def __init__(self, db):
        super().__init__(models.User, db)

    async def get_by_login(self, login: str) -> models.User | None:
        """Find user by email or username/login."""
        stmt = (
            select(models.User)
            .where(
                or_(
                    func.lower(models.User.email) == login.lower(),
                    # Assuming username or specific ID matching might be needed
                )
            )
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        group_id: int | None = None,
        full_name: str | None = None,
        role: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[models.User]:
        stmt = (
            select(models.User)
            .where(models.User.status != "deleted")
            .options(*USER_MFA_LOAD_OPTIONS, selectinload(models.User.group))
        )
        if group_id:
            stmt = stmt.where(models.User.group_id == group_id)
        if full_name:
            stmt = stmt.where(models.User.full_name.ilike(f"%{full_name}%"))
        if role:
            stmt = stmt.where(models.User.role == role)

        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def check_email_exists(
        self, email: str, exclude_user_id: int | None = None
    ) -> bool:
        stmt = select(exists().where(func.lower(models.User.email) == email.lower()))
        if exclude_user_id:
            stmt = stmt.where(models.User.id != exclude_user_id)
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
