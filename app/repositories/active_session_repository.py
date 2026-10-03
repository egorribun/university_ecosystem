from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm.interfaces import LoaderOption

from app.auth.mfa.lifecycle import (
    collect_mfa_session_revocations,
    publish_mfa_session_revocations,
)
from app.models import ActiveSession, User
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
        """Revoke sibling credentials in both PostgreSQL and Redis before commit."""
        return await self._revoke_sessions(user_id, current_session_id)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every credential in both PostgreSQL and Redis before commit."""
        return await self._revoke_sessions(user_id, None)

    async def _revoke_sessions(
        self, user_id: uuid.UUID, current_session_id: uuid.UUID | None
    ) -> int:
        pending = await collect_mfa_session_revocations(
            self.db, user_id=user_id, current_session_id=current_session_id
        )
        await publish_mfa_session_revocations(pending)
        return len(pending)
