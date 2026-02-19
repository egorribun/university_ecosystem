"""
Event repository for event data access operations.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.core.config import settings
from app.models import models
from app.models.models import Event
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class EventRepository(BaseRepository[Event, dict, dict]):
    """Repository for Event model operations."""

    @property
    def model(self) -> type[Event]:
        return Event

    async def get_with_details(self, event_id: uuid.UUID | str | int) -> Event | None:
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        stmt = (
            select(Event).where(Event.id == event_id).options(selectinload(Event.files))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_upcoming(self, *, skip: int = 0, limit: int = 20) -> list[Event]:
        """Get upcoming events ordered by start date."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Event)
            .where(Event.starts_at >= now)
            .order_by(Event.starts_at.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_organizer(
        self, organizer_id: uuid.UUID | str | int, *, skip: int = 0, limit: int = 20
    ) -> list[Event]:
        """Get events by organizer."""
        if isinstance(organizer_id, str):
            with contextlib.suppress(ValueError):
                organizer_id = uuid.UUID(organizer_id)
        result = await self.db.execute(
            select(Event)
            .where(Event.created_by == organizer_id)
            .order_by(Event.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_upcoming(self) -> int:
        """Count upcoming events."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(func.count(Event.id)).where(Event.starts_at >= now)
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
            .order_by(Event.starts_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_events(
        self,
        *,
        user_id: uuid.UUID | int | None = None,
        search_query: str = "",
        event_type: str | None = None,
        location: str | None = None,
        is_active: bool | None = True,
        limit: int = 20,
        cursor: tuple[datetime, uuid.UUID | int | str] | None = None,
        query_embedding: list[float] | None = None,
    ) -> Sequence[tuple[Event, int, models.EventAttendance | None]]:
        now = datetime.now(UTC)

        # Build conditions
        conditions = []
        rank_expr = None

        if search_query:
            ts_query = func.plainto_tsquery("simple", search_query)
            conditions.append(Event.search_vector.op("@@")(ts_query))
            rank_expr = func.ts_rank(Event.search_vector, ts_query)

            if (
                settings.semantic_search_enabled
                and query_embedding
                and any(abs(v) > 1e-9 for v in query_embedding)
            ):
                sim_score = 1.0 - Event.embedding.cosine_distance(query_embedding)
                rank_expr = (rank_expr + sim_score * 2.0).label("hybrid_rank")
                conditions = [or_(and_(*conditions), sim_score > 0.6)]

        if event_type:
            conditions.append(
                or_(
                    Event.event_type == event_type,
                    Event.event_type_en == event_type,
                )
            )

        if location:
            conditions.append(
                or_(
                    Event.location.ilike(f"%{location}%"),
                    Event.location_en.ilike(f"%{location}%"),
                )
            )

        if is_active is True:
            conditions.append(Event.ends_at >= now)
        elif is_active is False:
            conditions.append(Event.ends_at < now)

        if cursor:
            last_starts_at, last_id = cursor
            if isinstance(last_id, str):
                with contextlib.suppress(ValueError):
                    last_id = uuid.UUID(last_id)
            conditions.append(
                or_(
                    Event.starts_at > last_starts_at,
                    and_(
                        Event.starts_at == last_starts_at,
                        Event.id > last_id,
                    ),
                )
            )

        # Attendance counts and current user attendance
        participant_count_sub = (
            select(func.count())
            .where(models.EventAttendance.event_id == Event.id)
            .correlate(Event)
            .scalar_subquery()
            .label("participant_count")
        )

        user_attendance_alias = aliased(models.EventAttendance)
        join_cond = user_attendance_alias.event_id == Event.id
        if user_id:
            if isinstance(user_id, str):
                with contextlib.suppress(ValueError):
                    user_id = uuid.UUID(user_id)
            join_cond = and_(join_cond, user_attendance_alias.user_id == user_id)
        else:
            # Use a dummy UUID that won't exist
            join_cond = and_(
                join_cond,
                user_attendance_alias.user_id == uuid.UUID(int=0),
            )

        stmt = (
            select(Event, participant_count_sub, user_attendance_alias)
            .outerjoin(user_attendance_alias, join_cond)
            .options(selectinload(Event.files))
        )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        if rank_expr is not None:
            stmt = stmt.order_by(
                rank_expr.desc(), Event.starts_at.asc(), Event.id.asc()
            )
        else:
            stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc())

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.all()

    async def get_event_with_details(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str | None
    ) -> tuple[Event, int, models.EventAttendance | None] | None:
        """Fetch event with participant count and specific user attendance."""
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        if user_id and isinstance(user_id, str):
            with contextlib.suppress(ValueError):
                user_id = uuid.UUID(user_id)

        participant_count_sub = (
            select(func.count())
            .where(models.EventAttendance.event_id == event_id)
            .scalar_subquery()
            .label("participant_count")
        )

        user_attendance_alias = aliased(models.EventAttendance)
        stmt = (
            select(Event, participant_count_sub, user_attendance_alias)
            .outerjoin(
                user_attendance_alias,
                and_(
                    user_attendance_alias.event_id == event_id,
                    user_attendance_alias.user_id == user_id,
                ),
            )
            .where(Event.id == event_id)
            .options(selectinload(Event.files))
        )

        result = await self.db.execute(stmt)
        return result.first()

    async def get_attendance(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str
    ) -> models.EventAttendance | None:
        """Get user attendance for a specific event."""
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        if isinstance(user_id, str):
            with contextlib.suppress(ValueError):
                user_id = uuid.UUID(user_id)
        stmt = select(models.EventAttendance).where(
            models.EventAttendance.event_id == event_id,
            models.EventAttendance.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_attendance(self, **kwargs) -> models.EventAttendance:
        """Create a new event attendance record."""
        record = models.EventAttendance(**kwargs)
        self.db.add(record)
        await self.db.flush()
        return record

    async def delete_attendance(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str
    ) -> bool:
        """Delete user attendance for a specific event."""
        attendance = await self.get_attendance(event_id, user_id)
        if not attendance:
            return False
        await self.db.delete(attendance)
        return True

    async def list_user_attended_events(
        self, user_id: uuid.UUID | int | str
    ) -> list[Event]:
        """List all events a user has registered for."""
        if isinstance(user_id, str):
            with contextlib.suppress(ValueError):
                user_id = uuid.UUID(user_id)
        stmt = (
            select(Event)
            .join(models.EventAttendance)
            .where(models.EventAttendance.user_id == user_id)
            .options(selectinload(Event.files), selectinload(Event.attendance))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_event_file_urls(self, event_id: uuid.UUID | int | str) -> list[str]:
        """Get all file URLs associated with an event."""
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        stmt = select(models.EventFile.file_url).where(
            models.EventFile.event_id == event_id
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all() if row[0]]

    async def delete_event_files(self, event_id: uuid.UUID | int | str) -> None:
        """Delete all file records associated with an event."""
        from sqlalchemy import delete

        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        await self.db.execute(
            delete(models.EventFile).where(models.EventFile.event_id == event_id)
        )


def get_event_repository(db: AsyncSession) -> EventRepository:
    """Factory function for dependency injection."""
    return EventRepository(db)


__all__ = ["EventRepository", "get_event_repository"]
