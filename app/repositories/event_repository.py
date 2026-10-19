"""
Event repository for event data access operations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    and_,
    delete,
    func,
    literal,
    not_,
    or_,
    select,
    type_coerce,
    update,
)
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.orm.attributes import flag_dirty

import app.models as models
from app.core.config import settings
from app.core.events import EventCreated, EventUpdated
from app.core.protocols import AsyncDatabaseSession
from app.models import Event
from app.repositories.base import BaseRepository
from app.schemas.dtos import EventAttendanceDTO, EventDTO, EventSearchResultDTO

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.sql.elements import ColumnElement

    from app.core.protocols import AsyncDatabaseSession


class EventRepository(BaseRepository[Event, EventDTO, dict[str, Any], dict[str, Any]]):
    """Repository for Event model operations."""

    _MAX_USER_ATTENDED_EVENTS_QUERY_LIMIT = 101

    _EVENT_CATEGORY_PATTERNS: ClassVar[dict[str, str]] = {
        "lecture": r"лекци|lecture|занят|class|lesson",
        "seminar": r"семинар|seminar|коллоквиум|colloquium|круглый.?стол|round.?table",
        "conference": r"конференц|conference|форум|forum|саммит|summit|симпозиум|symposium",
        "workshop": r"мастер.?класс|workshop|тренинг|training|воркшоп|практикум|practicum",
        "social": r"встреча|meetup|вечер|party|концерт|concert|фестиваль|festival|выставка|exhibition|праздник|celebration",
        "sport": r"спорт|sport|футбол|football|баскетбол|basketball|турнир|tournament|соревнован|competition|забег|race",
    }

    def __init__(self, db: AsyncDatabaseSession):
        super().__init__(db)

    async def create(
        self, obj_in: dict[str, Any], *, locale: str | None = None
    ) -> EventDTO:
        result = await super().create(obj_in)
        record = await self._get_orm(result.id)
        assert record is not None  # noqa: S101
        record.record_event(
            EventCreated(
                event_id_entity=record.id,
                title=record.title,
                organizer_id=record.created_by,
                locale=locale,
            )
        )
        # Capture in this transaction so rollback cannot retain an emitter.
        flag_dirty(record)
        await self.db.flush()
        return result

    async def update(self, id: Any, obj_in: dict[str, Any]) -> EventDTO | None:
        result = await super().update(id, obj_in)
        if result is not None:
            record = await self._get_orm(result.id)
            assert record is not None  # noqa: S101
            record.record_event(
                EventUpdated(event_id_entity=record.id, title=record.title)
            )
            # Capture in this transaction so rollback cannot retain an emitter.
            flag_dirty(record)
            await self.db.flush()
        return result

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

    def _build_search_conditions(
        self,
        *,
        search_query: str,
        event_type: str | None,
        location: str | None,
        is_active: bool | None,
        query_embedding: list[float] | None,
        now: datetime,
    ) -> tuple[list[Any], ColumnElement[float] | None]:
        conditions: list[Any] = []
        rank_expr: ColumnElement[float] | None = None

        if search_query:
            ts_query = func.plainto_tsquery("simple", search_query)
            conditions.append(Event.search_vector.op("@@")(ts_query))
            rank_expr = func.coalesce(func.ts_rank(Event.search_vector, ts_query), 0.0)

            if (
                settings.semantic_search_enabled
                and query_embedding
                and any(abs(v) > 1e-9 for v in query_embedding)
            ):
                distance = type_coerce(Event.embedding, Vector(1536)).cosine_distance(
                    query_embedding
                )
                # Legacy zero-norm vectors produce NaN in pgvector. Treat these
                # as absent embeddings in both ranking and cursor predicates.
                sim_score = 1.0 - func.nullif(distance, float("nan"))
                rank_expr = (rank_expr + func.coalesce(sim_score, 0.0) * 2.0).label(
                    "hybrid_rank"
                )
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

        # Event.is_active is the manual-hide flag: hidden events are excluded from
        # listings and totals alike. The is_active argument only selects upcoming
        # (True) or archived, i.e. already ended (False), events.
        conditions.append(Event.is_active.is_(True))
        if is_active is True:
            conditions.append(Event.ends_at >= now)
        elif is_active is False:
            conditions.append(Event.ends_at < now)

        return conditions, rank_expr

    async def count_search_events(
        self,
        *,
        search_query: str = "",
        event_type: str | None = None,
        location: str | None = None,
        is_active: bool | None = True,
        query_embedding: list[float] | None = None,
        now: datetime | None = None,
    ) -> int:
        """Count the same filtered event set used by the list query."""
        current_time = now or datetime.now(UTC)
        conditions, _ = self._build_search_conditions(
            search_query=search_query,
            event_type=event_type,
            location=location,
            is_active=is_active,
            query_embedding=query_embedding,
            now=current_time,
        )
        stmt = select(func.count(Event.id))
        # The shared builder always includes the manual-visibility predicate.
        stmt = stmt.where(and_(*conditions))
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def search_events(
        self,
        *,
        user_id: uuid.UUID | int | str | None = None,
        search_query: str = "",
        event_type: str | None = None,
        location: str | None = None,
        is_active: bool | None = True,
        limit: int = 20,
        cursor: tuple[datetime, uuid.UUID | int | str]
        | tuple[datetime, str, float | None]
        | None = None,
        order: Literal["starts_at_asc", "starts_at_desc"] | None = None,
        query_embedding: list[float] | None = None,
        now: datetime | None = None,
    ) -> Sequence[EventSearchResultDTO]:
        now = now or datetime.now(UTC)

        conditions, rank_expr = self._build_search_conditions(
            search_query=search_query,
            event_type=event_type,
            location=location,
            is_active=is_active,
            query_embedding=query_embedding,
            now=now,
        )

        if cursor:
            last_starts_at, raw_id = cursor[:2]
            last_id = self._cast_id(raw_id)
            if order == "starts_at_desc":
                after_time = or_(
                    Event.starts_at < last_starts_at,
                    and_(Event.starts_at == last_starts_at, Event.id < last_id),
                )
            else:
                after_time = or_(
                    Event.starts_at > last_starts_at,
                    and_(Event.starts_at == last_starts_at, Event.id > last_id),
                )
            if rank_expr is not None and order is None:
                last_rank = (
                    cursor[2]
                    if len(cursor) == 3
                    else await self.db.scalar(
                        select(rank_expr).where(Event.id == last_id)
                    )
                )
                if last_rank is None:
                    return []
                conditions.append(
                    or_(rank_expr < last_rank, and_(rank_expr == last_rank, after_time))
                )
            else:
                conditions.append(after_time)

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

        # The shared builder always includes the manual-visibility predicate.
        stmt = stmt.where(and_(*conditions))

        if rank_expr is not None:
            stmt = stmt.add_columns(rank_expr)
        if order == "starts_at_desc":
            stmt = stmt.order_by(Event.starts_at.desc(), Event.id.desc())
        elif order == "starts_at_asc":
            stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc())
        elif rank_expr is not None:
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
                rank=float(row[3]) if rank_expr is not None else None,
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
        self,
        user_id: uuid.UUID | int | str,
        *,
        limit: int,
        locale: str,
        category: str | None = None,
        starts_at_from: datetime | None = None,
        starts_at_before: datetime | None = None,
        upcoming_after: datetime | None = None,
        sort: str = "newest",
        cursor_key: tuple[datetime | int, uuid.UUID] | None = None,
        include_participant_count: bool = True,
    ) -> list[tuple[Event, models.EventAttendance, int]]:
        """Fetch one bounded page after applying owner and display filters.

        The owner attendance predicate and all user-visible predicates run in
        SQL before LIMIT. The unique ``(user_id, event_id)`` constraint keeps
        the join one-row-per-event, and no attendance/files collection is
        eagerly loaded. Popularity uses the same correlated count strategy as
        ``search_events`` so the page order does not aggregate the whole table.
        """
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= self._MAX_USER_ATTENDED_EVENTS_QUERY_LIMIT
        ):
            raise ValueError("My-events query limit must be between 1 and 101")
        user_id = self._cast_id(user_id)
        if sort not in {"newest", "popular", "upcoming"}:
            raise ValueError("Unsupported event sort")
        if category is not None and category not in {
            *self._EVENT_CATEGORY_PATTERNS,
            "other",
        }:
            raise ValueError("Unsupported event category")

        localized_type = (
            func.coalesce(func.nullif(Event.event_type, ""), Event.event_type_en)
            if locale == "ru"
            else func.coalesce(func.nullif(Event.event_type_en, ""), Event.event_type)
        )
        participant_count = (
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == Event.id)
            .correlate(Event)
            .scalar_subquery()
            if include_participant_count
            else literal(0)
        )
        stmt = (
            select(
                Event,
                models.EventAttendance,
                participant_count.label("participant_count"),
            )
            .join(
                models.EventAttendance,
                models.EventAttendance.event_id == Event.id,
            )
            .where(models.EventAttendance.user_id == user_id)
        )
        if category is not None:
            ordered_patterns = list(self._EVENT_CATEGORY_PATTERNS.items())
            matches = [
                localized_type.regexp_match(pattern, flags="i")
                for _, pattern in ordered_patterns
            ]
            if category == "other":
                stmt = stmt.where(or_(localized_type.is_(None), not_(or_(*matches))))
            else:
                selected_index = next(
                    index
                    for index, (category_id, _) in enumerate(ordered_patterns)
                    if category_id == category
                )
                stmt = stmt.where(matches[selected_index])
                if selected_index > 0:
                    stmt = stmt.where(not_(or_(*matches[:selected_index])))
        if starts_at_from is not None:
            stmt = stmt.where(Event.starts_at >= starts_at_from)
        if starts_at_before is not None:
            stmt = stmt.where(Event.starts_at < starts_at_before)
        if upcoming_after is not None:
            stmt = stmt.where(Event.starts_at > upcoming_after)

        if cursor_key is not None:
            cursor_value, cursor_event_id = cursor_key
            if sort in {"newest", "upcoming"}:
                if not isinstance(cursor_value, datetime):
                    raise ValueError("Invalid date-ordered cursor key")
                stmt = stmt.where(
                    or_(
                        Event.starts_at > cursor_value,
                        and_(
                            Event.starts_at == cursor_value, Event.id > cursor_event_id
                        ),
                    )
                )
            else:
                if isinstance(cursor_value, bool) or not isinstance(cursor_value, int):
                    raise ValueError("Invalid popular cursor key")
                stmt = stmt.where(
                    or_(
                        participant_count < cursor_value,
                        and_(
                            participant_count == cursor_value,
                            Event.id < cursor_event_id,
                        ),
                    )
                )

        if sort in {"newest", "upcoming"}:
            stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc())
        else:
            stmt = stmt.order_by(participant_count.desc(), Event.id.desc())
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [(row[0], row[1], int(row[2] or 0)) for row in result.all()]

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
