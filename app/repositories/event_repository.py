"""
Event repository for event data access operations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import aliased, selectinload

import app.models as models
from app.core.config import settings
from app.core.protocols import AsyncDatabaseSession
from app.models import Event
from app.repositories.base import BaseRepository
from app.schemas.dtos import EventAttendanceDTO, EventDTO, EventSearchResultDTO

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.protocols import AsyncDatabaseSession


class EventRepository(BaseRepository[Event, EventDTO, dict[str, Any], dict[str, Any]]):
    """Repository for Event model operations."""

    def __init__(self, db: AsyncDatabaseSession):
        super().__init__(db)

    @property
    def model(self) -> type[Event]:
        return Event

    @property
    def dto_class(self) -> type[EventDTO]:
        return EventDTO

    async def get_for_registration(
        self, event_id: uuid.UUID | str | int
    ) -> Event | None:
        """Fetch an Event row with SELECT FOR UPDATE.

        P2-W5-15: Serializes concurrent attendance registrations so that
        is_active / ends_at checks and the INSERT are in the same DB-level
        critical section.  Returns the ORM object (not a DTO) so callers can
        revalidate fields and the row stays locked for the transaction duration.
        """
        event_id = self._cast_id(event_id)
        stmt = select(Event).where(Event.id == event_id).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_details(
        self, event_id: uuid.UUID | str | int
    ) -> EventDTO | None:
        event_id = self._cast_id(event_id)
        stmt = (
            select(Event).where(Event.id == event_id).options(selectinload(Event.files))
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return self._to_dto(obj) if obj else None

    async def get_upcoming(
        self,
        *,
        limit: int = 20,
        after_starts_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[EventDTO]:
        """Get upcoming events with keyset cursor pagination.

        AUDIT-BE-01 (audit 2026-03-15): Replaced OFFSET-based pagination.
        OFFSET forces PostgreSQL to scan and discard all preceding rows — O(N).
        Keyset pagination uses a composite (starts_at, id) cursor to jump
        directly to the next page via the existing B-tree index — O(log N).

        Callers that previously used skip=N should compute an (after_starts_at,
        after_id) cursor from the last item of the previous page.
        """
        now = datetime.now(UTC)
        stmt = select(Event).where(Event.starts_at >= now)
        if after_starts_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Event.starts_at > after_starts_at,
                    and_(Event.starts_at == after_starts_at, Event.id > after_id),
                )
            )
        stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(limit)
        objs = (await self.db.execute(stmt)).scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_by_organizer(
        self,
        organizer_id: uuid.UUID | str | int,
        *,
        limit: int = 20,
        after_created_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[EventDTO]:
        """Get events by organizer with keyset cursor pagination.

        AUDIT-BE-01 (audit 2026-03-15): Replaced OFFSET with keyset cursor.
        Cursor is composite (created_at DESC, id DESC) matching the ORDER BY clause
        so the B-tree index on created_at can be used directly without a sort step.
        """
        organizer_id = self._cast_id(organizer_id)
        stmt = select(Event).where(Event.created_by == organizer_id)
        if after_created_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Event.created_at < after_created_at,
                    and_(Event.created_at == after_created_at, Event.id < after_id),
                )
            )
        stmt = stmt.order_by(Event.created_at.desc(), Event.id.desc()).limit(limit)
        objs = (await self.db.execute(stmt)).scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count_upcoming(self) -> int:
        """Count upcoming events."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(func.count(Event.id)).where(Event.starts_at >= now)
        )
        return result.scalar() or 0

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
        after_starts_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[EventDTO]:
        """Search events by title (case-insensitive) using keyset pagination."""
        # CRIT-01 (audit 2026-03-11): Escape LIKE wildcards before embedding.
        safe_query = self._escape_like(query.strip().lower())
        pattern = f"%{safe_query}%"

        stmt = select(Event).where(func.lower(Event.title).like(pattern, escape="\\"))
        if after_starts_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Event.starts_at < after_starts_at,
                    and_(Event.starts_at == after_starts_at, Event.id < after_id),
                )
            )

        stmt = stmt.order_by(Event.starts_at.desc(), Event.id.desc()).limit(limit)

        result = await self.db.execute(stmt)
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
            safe_type = self._escape_like(event_type)
            conditions.append(
                or_(
                    Event.event_type.ilike(f"%{safe_type}%", escape="\\"),
                    Event.event_type_en.ilike(f"%{safe_type}%", escape="\\"),
                )
            )

        if location:
            # CRIT-01 (audit 2026-03-11): Escape ILIKE wildcards before embedding.
            safe_loc = self._escape_like(location)
            conditions.append(
                or_(
                    Event.location.ilike(f"%{safe_loc}%", escape="\\"),
                    Event.location_en.ilike(f"%{safe_loc}%", escape="\\"),
                )
            )

        if is_active is True:
            conditions.append(Event.ends_at >= now)
        elif is_active is False:
            conditions.append(Event.ends_at < now)

        if cursor:
            last_starts_at, last_id = cursor
            last_id = self._cast_id(last_id)
            conditions.append(
                or_(
                    Event.starts_at > last_starts_at,
                    and_(
                        Event.starts_at == last_starts_at,
                        Event.id > last_id,
                    ),
                )
            )

        # PERF-W10-02: Replaced the global aggregating CTE with a correlated
        # scalar subquery.  The CTE scanned the entire event_attendance table
        # in a single HashAggregate before the main query's LIMIT could apply —
        # O(total_attendance_rows) memory on the DB server.  With a composite
        # index on event_attendance(event_id) the correlated COUNT(*) executes
        # an index scan per result row: O(limit * log(attendance_per_event))
        # which is far cheaper when limit ≤ 50.
        participant_count_col = (
            select(func.count())
            .where(models.EventAttendance.event_id == Event.id)
            .correlate(Event)
            .scalar_subquery()
            .label("participant_count")
        )

        user_attendance_alias = aliased(models.EventAttendance)
        join_cond = user_attendance_alias.event_id == Event.id
        if user_id:
            user_id = self._cast_id(user_id)
            join_cond = and_(join_cond, user_attendance_alias.user_id == user_id)
        else:
            # Use a dummy UUID that won't exist
            join_cond = and_(
                join_cond,
                user_attendance_alias.user_id == uuid.UUID(int=0),
            )

        stmt = (
            select(
                Event,
                participant_count_col,
                user_attendance_alias,
            )
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
        event_id = self._cast_id(event_id)
        if user_id:
            user_id = self._cast_id(user_id)

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
        event_id = self._cast_id(event_id)
        user_id = self._cast_id(user_id)
        stmt = select(models.EventAttendance).where(
            models.EventAttendance.event_id == event_id,
            models.EventAttendance.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return EventAttendanceDTO.model_validate(obj) if obj else None

    async def create_attendance(self, **kwargs: Any) -> EventAttendanceDTO:
        """Create a new event attendance record."""
        record = models.EventAttendance(**kwargs)
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return EventAttendanceDTO.model_validate(record)

    async def delete_attendance(
        self, event_id: uuid.UUID | int | str, user_id: uuid.UUID | int | str
    ) -> bool:
        """Delete user attendance for a specific event."""
        event_id = self._cast_id(event_id)
        user_id = self._cast_id(user_id)
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
        event_id = self._cast_id(event_id)
        user_id = self._cast_id(user_id)

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
    ) -> list[Event]:
        """List all events a user has registered for."""
        user_id = self._cast_id(user_id)
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
        event_id = self._cast_id(event_id)
        stmt = select(models.EventFile.file_url).where(
            models.EventFile.event_id == event_id
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all() if row[0]]

    async def delete_event_files(self, event_id: uuid.UUID | int | str) -> None:
        """Delete all file records associated with an event."""
        from sqlalchemy import delete

        event_id = self._cast_id(event_id)
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

    async def get_event_files(
        self, event_id: uuid.UUID | str | int
    ) -> list[models.EventFile]:
        """Fetch all attachments for the given event."""
        event_id = self._cast_id(event_id)
        stmt = select(models.EventFile).where(models.EventFile.event_id == event_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


def get_event_repository(db: AsyncDatabaseSession) -> EventRepository:
    """Factory function for dependency injection."""
    return EventRepository(db)


__all__ = ["EventRepository", "get_event_repository"]
