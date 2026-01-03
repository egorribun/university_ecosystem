"""
Event repository for event data access operations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event, dict, dict]):
    """Repository for Event model operations."""

    @property
    def model(self) -> type[Event]:
        return Event

    async def get_upcoming(self, *, skip: int = 0, limit: int = 20) -> list[Event]:
        """Get upcoming events ordered by start date."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Event)
            .where(Event.start_date >= now)
            .order_by(Event.start_date.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_organizer(
        self, organizer_id: int, *, skip: int = 0, limit: int = 20
    ) -> list[Event]:
        """Get events by organizer."""
        result = await self.db.execute(
            select(Event)
            .where(Event.organizer_id == organizer_id)
            .order_by(Event.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_upcoming(self) -> int:
        """Count upcoming events."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(func.count(Event.id)).where(Event.start_date >= now)
        )
        return result.scalar() or 0

    async def search(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[Event]:
        """Search events by title (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(Event)
            .where(func.lower(Event.title).like(pattern))
            .order_by(Event.start_date.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


def get_event_repository(db: AsyncSession) -> EventRepository:
    """Factory function for dependency injection."""
    return EventRepository(db)


__all__ = ["EventRepository", "get_event_repository"]
