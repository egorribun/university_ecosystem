"""
Session repository for session data access operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, func, select, update

from app.models.auth import ActiveSession
from app.repositories.base import BaseRepository
from app.schemas.dtos.session import ActiveSessionDTO

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class SessionRepository(BaseRepository[ActiveSession, ActiveSessionDTO, dict, dict]):
    """Repository for ActiveSession model operations."""

    @property
    def model(self) -> type[ActiveSession]:
        return ActiveSession

    @property
    def dto_class(self) -> type[ActiveSessionDTO]:
        return ActiveSessionDTO

    async def get_by_jti(self, jti: str) -> ActiveSessionDTO | None:
        """Get session by JTI (JWT ID)."""
        result = await self.db.execute(
            select(ActiveSession).where(ActiveSession.jti == jti)
        )
        row = result.scalars().first()
        return self._to_dto(row) if row else None

    async def get_active_for_user(
        self, user_id: uuid.UUID | str | int, *, skip: int = 0, limit: int = 50
    ) -> list[ActiveSessionDTO]:
        """Get active sessions for a user, ordered by last_seen_at descending."""
        result = await self.db.execute(
            select(ActiveSession)
            .where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            .order_by(ActiveSession.last_seen_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [self._to_dto(row) for row in result.scalars().all()]

    async def count_active_for_user(self, user_id: uuid.UUID | str | int) -> int:
        """Count active sessions for a user."""
        result = await self.db.execute(
            select(func.count(ActiveSession.id)).where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.revoked_at.is_(None),
                )
            )
        )
        return result.scalar() or 0

    async def revoke(
        self, session_id: uuid.UUID | str | int, user_id: uuid.UUID | str | int
    ) -> bool:
        """Revoke a specific session. Returns True if session was revoked."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(ActiveSession)
            .where(
                and_(
                    ActiveSession.id == session_id,
                    ActiveSession.user_id == user_id,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            .values(revoked_at=now)
        )
        await self.db.flush()
        return (int(getattr(result, "rowcount", 0) or 0)) > 0

    async def revoke_by_jti(self, jti: str) -> bool:
        """Revoke a session by JTI."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(ActiveSession)
            .where(
                and_(
                    ActiveSession.jti == jti,
                    ActiveSession.revoked_at.is_(None),
                )
            )
            .values(revoked_at=now)
        )
        await self.db.flush()
        return (int(getattr(result, "rowcount", 0) or 0)) > 0

    async def revoke_all_except(
        self, user_id: uuid.UUID | str | int, current_session_id: uuid.UUID | str | int
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

    async def revoke_all_for_user(self, user_id: uuid.UUID | str | int) -> int:
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

    async def cleanup_expired(self, max_age_days: int = 30) -> int:
        """Delete sessions older than max_age_days. Returns count deleted."""
        cutoff = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        # Subtract days manually for clarity
        from datetime import timedelta

        cutoff = cutoff - timedelta(days=max_age_days)

        result = await self.db.execute(
            delete(ActiveSession).where(ActiveSession.created_at < cutoff)
        )
        await self.db.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def touch(self, session_id: uuid.UUID | str | int) -> None:
        """Update last_seen_at timestamp for a session."""
        now = datetime.now(UTC)
        await self.db.execute(
            update(ActiveSession)
            .where(ActiveSession.id == session_id)
            .values(last_seen_at=now)
        )
        await self.db.flush()


def get_session_repository(db: AsyncSession) -> SessionRepository:
    """Factory function for dependency injection."""
    return SessionRepository(db)


__all__ = ["SessionRepository", "get_session_repository"]
