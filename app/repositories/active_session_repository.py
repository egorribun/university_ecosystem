import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import load_only
from sqlalchemy.sql.elements import ClauseElement

from app.models.models import ActiveSession
from app.repositories.base import ReadOnlyRepository


class ActiveSessionRepository(ReadOnlyRepository[ActiveSession]):
    @property
    def model(self) -> type[ActiveSession]:
        return ActiveSession

    async def create(self, data: dict) -> ActiveSession:
        obj = ActiveSession(**data)
        self.db.add(obj)
        return obj

    async def get_by_jti(self, jti: str) -> ActiveSession | None:
        stmt = select(ActiveSession).where(ActiveSession.jti == jti)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_count_for_user(self, user_id: uuid.UUID, now: datetime) -> int:
        stmt = (
            select(func.count(ActiveSession.id))
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.revoked_at.is_(None))
            .where(ActiveSession.expires_at > now)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or 0

    async def get_oldest_active_sessions(
        self,
        user_id: uuid.UUID,
        now: datetime,
        limit: int,
        exclude_jti: str | None = None,
    ) -> Sequence[ActiveSession]:
        stmt = (
            select(ActiveSession)
            .options(load_only(ActiveSession.id, ActiveSession.jti))
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.revoked_at.is_(None))
            .where(ActiveSession.expires_at > now)
        )
        if exclude_jti:
            stmt = stmt.where(ActiveSession.jti != exclude_jti)

        stmt = stmt.order_by(ActiveSession.created_at.asc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def revoke_by_id(self, session_id: uuid.UUID, now: datetime) -> bool:
        session = await self.db.get(ActiveSession, session_id)
        if session:
            session.revoked_at = now
            return True
        return False

    async def delete_matching(self, whereclause: ClauseElement[bool]) -> int:
        stmt = delete(ActiveSession).where(whereclause)
        result = await self.db.execute(stmt)
        return int(result.rowcount or 0)
