from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.orm.interfaces import LoaderOption
from sqlalchemy.sql.elements import ClauseElement

from app.core.protocols import AsyncDatabaseSession
from app.models.models import ActiveSession, User
from app.repositories.base import BaseRepository
from app.schemas.dtos import ActiveSessionDTO


class ActiveSessionRepository(
    BaseRepository[ActiveSession, ActiveSessionDTO, dict[str, Any], dict[str, Any]]
):
    @property
    def model(self) -> type[ActiveSession]:
        return ActiveSession

    @property
    def dto_class(self) -> type[ActiveSessionDTO]:
        return ActiveSessionDTO

    async def create(self, data: dict[str, Any]) -> ActiveSessionDTO:
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
        return result.scalar() or 0

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
        return cast(int, getattr(result, "rowcount", 0) or 0)

    async def get_active_session_with_user(
        self,
        user_id: uuid.UUID,
        jti: str,
        load_options: list[LoaderOption] | None = None,
    ) -> tuple[User, ActiveSession] | None:
        """Single-query JOIN fetch for auth hot-path (avoids N+1).

        Returns (User, ActiveSession) if a non-revoked, active session exists,
        or None if any of the following conditions fail:
          - user not found or inactive
          - session jti not found
          - session already revoked
        """
        stmt = (
            select(User, ActiveSession)
            .join(ActiveSession, ActiveSession.user_id == User.id)
            .where(User.id == user_id, User.is_active.is_(True))
            .where(ActiveSession.jti == jti)
            .where(ActiveSession.revoked_at.is_(None))
        )
        if load_options:
            stmt = stmt.options(*load_options)
        result = await self.db.execute(stmt)
        row = result.first()
        if not row:
            return None
        return cast(tuple[User, ActiveSession], (row[0], row[1]))

    async def revoke_all_except(
        self, user_id: uuid.UUID, current_session_id: uuid.UUID
    ) -> int:
        """Revoke all sessions except the current one. Returns count of revoked."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(ActiveSession)
            .where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.id != current_session_id,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            .values(revoked_at=now)
        )
        await self.db.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all sessions for a user. Returns count of revoked."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(ActiveSession)
            .where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            .values(revoked_at=now)
        )
        await self.db.flush()
        return int(getattr(result, "rowcount", 0) or 0)


def get_active_session_repository(db: AsyncDatabaseSession) -> ActiveSessionRepository:
    return ActiveSessionRepository(db)
