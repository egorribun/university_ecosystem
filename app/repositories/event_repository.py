"""
Event repository for event data access operations.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import aliased, selectinload

from app.core.protocols import AsyncDatabaseSession
from app.core.config import settings
from app.models import models
from app.models.models import Event
from app.repositories.base import BaseRepository
from app.schemas.dtos import EventAttendanceDTO, EventDTO, EventSearchResultDTO

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.protocols import AsyncDatabaseSession


class EventRepository(BaseRepository[Event, EventDTO, dict, dict]):
    """Repository for Event model operations."""

    def __init__(self, db: AsyncDatabaseSession):
        self.db = db

    @property
    def model(self) -> type[Event]:
        return Event

    @property
    def dto_class(self) -> type[EventDTO]:
        return EventDTO

    async def get_with_details(
        self, event_id: uuid.UUID | str | int
    ) -> EventDTO | None:
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        stmt = (
            select(Event).where(Event.id == event_id).options(selectinload(Event.files))
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return self._to_dto(obj) if obj else None

    async def get_upcoming(self, *, skip: int = 0, limit: int = 20) -> list[EventDTO]:
        """Get upcoming events ordered by start date."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Event)
            .where(Event.starts_at >= now)
            .order_by(Event.starts_at.asc())
            .offset(skip)
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_by_organizer(
        self, organizer_id: uuid.UUID | str | int, *, skip: int = 0, limit: int = 20
    ) -> list[EventDTO]:
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
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count_upcoming(self) -> int:
        """Count upcoming events."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(func.count(Event.id)).where(Event.starts_at >= now)
        )
        return result.scalar() or 0

    async def search(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[EventDTO]:
        """Search events by title (case-insensitive)."""
        pattern = f"%{query.strip().lower()}%"
        result = await self.db.execute(
            select(Event)
            .where(func.lower(Event.title).like(pattern))
            .order_by(Event.starts_at.desc())
            .offset(skip)
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def search_events(
        self,
        *,
        user_id: uuid.UUID | int | str | None = None,
        search_query: str = "",
        event_type: str | None = None,
        location: str | None = None,
        is_active: bool | None = True,
        limit: int = 20,
        cursor: tuple[datetime, uuid.UUID | int | str] | None = None,
        query_embedding: list[float] | None = None,
    ) -> Sequence[EventSearchResultDTO]:
        now = datetime.now(UTC)

        # Build conditions
        conditions: list[Any] = []
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
        rows = result.all()
        from app.schemas.dtos.event import EventAttendanceDTO, EventSearchResultDTO

        return [
            EventSearchResultDTO(
                event=row[0] if isinstance(row[0], EventDTO) else self._to_dto(row[0]),
                participant_count=row[1] or 0,
                user_attendance=EventAttendanceDTO.model_validate(row[2])
                if row[2]
                else None,
            )
            for row in rows
        ]

    async def get_event_with_details(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str | None
    ) -> EventSearchResultDTO | None:
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
        first = result.first()
        if not first:
            return None

        attendance_dto = (
            EventAttendanceDTO.model_validate(first[2]) if first[2] else None
        )
        from app.schemas.dtos.event import EventSearchResultDTO

        return EventSearchResultDTO(
            event=self._to_dto(first[0]),
            participant_count=first[1] or 0,
            user_attendance=attendance_dto,
        )

    async def get_attendance(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str
    ) -> EventAttendanceDTO | None:
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
        obj = result.scalar_one_or_none()
        return EventAttendanceDTO.model_validate(obj) if obj else None

    async def create_attendance(self, **kwargs) -> EventAttendanceDTO:
        """Create a new event attendance record."""
        record = models.EventAttendance(**kwargs)
        self.db.add(record)
        await self.db.flush()
        return EventAttendanceDTO.model_validate(record)

    async def delete_attendance(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str
    ) -> bool:
        """Delete user attendance for a specific event."""
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        if isinstance(user_id, str):
            with contextlib.suppress(ValueError):
                user_id = uuid.UUID(user_id)
        stmt = delete(models.EventAttendance).where(
            models.EventAttendance.event_id == event_id,
            models.EventAttendance.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return bool(getattr(result, "rowcount", 0))

    async def update_attendance(
        self,
        event_id: uuid.UUID | int | str,
        user_id: uuid.UUID | int | str,
        updates: dict[str, Any],
    ) -> EventAttendanceDTO | None:
        """Update user attendance for a specific event."""
        if isinstance(event_id, str):
            with contextlib.suppress(ValueError):
                event_id = uuid.UUID(event_id)
        if isinstance(user_id, str):
            with contextlib.suppress(ValueError):
                user_id = uuid.UUID(user_id)

        stmt = (
            update(models.EventAttendance)
            .where(
                models.EventAttendance.event_id == event_id,
                models.EventAttendance.user_id == user_id,
            )
            .values(**updates)
            .returning(models.EventAttendance)
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return EventAttendanceDTO.model_validate(obj) if obj else None

    async def list_user_attended_events(
        self, user_id: uuid.UUID | int | str
    ) -> list[EventDTO]:
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
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

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

    async def get_analytics_data(
        self, start_date: datetime | None = None
    ) -> tuple[Sequence[Any], Sequence[str]]:
        """Fetch raw event data for high-performance Polars analytics."""
        from sqlalchemy import text

        query = """
            SELECT
                e.id, e.title, e.starts_at as start_time, e.location,
                COUNT(ea.user_id) as attendees_count,
                e.max_attendees
            FROM events e
            LEFT JOIN event_attendance ea ON e.id = ea.event_id
            WHERE e.deleted_at IS NULL
        """
        params: dict[str, Any] = {}

        if start_date:
            query += " AND e.starts_at >= :start_date"
            params["start_date"] = start_date

        query += " GROUP BY e.id, e.title, e.starts_at, e.location, e.max_attendees"

        result = await self.db.execute(text(query), params)
        return result.fetchall(), list(result.keys())


def get_event_repository(db: AsyncDatabaseSession) -> EventRepository:
    """Factory function for dependency injection."""
    return EventRepository(db)


__all__ = ["EventRepository", "get_event_repository"]
