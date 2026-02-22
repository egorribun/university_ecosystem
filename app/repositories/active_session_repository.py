import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.sql.elements import ClauseElement

from app.models.models import ActiveSession
from app.repositories.base import BaseRepository
from app.schemas.dtos import ActiveSessionDTO


class ActiveSessionRepository(BaseRepository[ActiveSession, ActiveSessionDTO, dict, dict]):
    @property
    def model(self) -> type[ActiveSession]:
        return ActiveSession

    @property
    def dto_class(self) -> type[ActiveSessionDTO]:
        return ActiveSessionDTO

    async def create(self, data: dict) -> ActiveSessionDTO:
        obj = ActiveSession(**data)
        self.db.add(obj)
        await self.db.flush()
        return self.dto_class.model_validate(obj)

    async def get_by_jti(self, jti: str) -> ActiveSessionDTO | None:
        stmt = select(ActiveSession).where(ActiveSession.jti == jti)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_dto(row) if row else None

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
    ) -> Sequence[ActiveSessionDTO]:
        stmt = (
            select(ActiveSession)
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.revoked_at.is_(None))
            .where(ActiveSession.expires_at > now)
        )
        if exclude_jti:
            stmt = stmt.where(ActiveSession.jti != exclude_jti)

        stmt = stmt.order_by(ActiveSession.created_at.asc()).limit(limit)
        result = await self.db.execute(stmt)
        return [self.dto_class.model_validate(s) for s in result.scalars().all()]

    async def revoke_by_id(self, session_id: uuid.UUID, now: datetime) -> bool:
        session = await self.db.get(ActiveSession, session_id)
        if session:
            session.revoked_at = now
            return True
        return False

    async def delete_matching(self, whereclause: ClauseElement) -> int:
        stmt = delete(ActiveSession).where(whereclause)  # type: ignore[arg-type]
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
