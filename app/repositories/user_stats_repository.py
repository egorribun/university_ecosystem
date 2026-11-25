from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import (
    Boolean,
    Float,
    String,
    and_,
    case,
    literal,
    null,
    select,
    union_all,
)
from sqlalchemy import (
    cast as sql_cast,
)
from sqlalchemy.sql.selectable import CompoundSelect, Select

import app.models as models
from app.repositories.base import ReadOnlyRepository
from app.schemas.dtos import UserDTO
from app.schemas.dtos.analytics import ParticipationStatsDTO


@dataclass(frozen=True, slots=True)
class UserAttendanceRow:
    starts_at: datetime
    title: str | None
    registered_at: datetime | None
    is_registered: bool


@dataclass(frozen=True, slots=True)
class UserGradeRow:
    created_at: datetime
    subject: str
    score: float


@dataclass(slots=True)
class UserSummaryRows:
    attendance: list[UserAttendanceRow] = field(default_factory=list)
    grades: list[UserGradeRow] = field(default_factory=list)
    participation: list[ParticipationStatsDTO] = field(default_factory=list)


def _as_utc(value: datetime) -> datetime:
    # Match UserAnalyticsService: SQLite returns naive UTC timestamps.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _attendance_statement(
    user_id: uuid.UUID | str,
    window_start: datetime,
    previous_start: datetime,
    now: datetime,
) -> CompoundSelect[Any]:
    attendance = models.EventAttendance
    registered_current = and_(
        models.Event.starts_at >= window_start,
        attendance.id.isnot(None),
    )
    window_events = (
        select(
            models.Event.starts_at.label("starts_at"),
            case((registered_current, models.Event.title), else_=None).label("title"),
            case((registered_current, attendance.registered_at), else_=None).label(
                "registered_at"
            ),
            attendance.id.isnot(None).label("is_registered"),
        )
        .select_from(models.Event)
        .outerjoin(
            attendance,
            and_(
                attendance.event_id == models.Event.id,
                attendance.user_id == user_id,
            ),
        )
        .where(
            models.Event.is_active.is_(True),
            models.Event.starts_at >= previous_start,
            models.Event.starts_at < now,
        )
    )
    history_events = (
        select(
            models.Event.starts_at.label("starts_at"),
            literal(None, type_=models.Event.title.type).label("title"),
            literal(None, type_=attendance.registered_at.type).label("registered_at"),
            literal(True).label("is_registered"),
        )
        .select_from(attendance)
        .join(models.Event, models.Event.id == attendance.event_id)
        .where(
            attendance.user_id == user_id,
            models.Event.is_active.is_(True),
            models.Event.starts_at < previous_start,
            models.Event.starts_at < now,
        )
    )
    # The service sorts only current registered rows for the capped recent feed.
    return union_all(window_events, history_events)


def _grades_statement(
    user_id: uuid.UUID | str, start_date: datetime, end_date: datetime
) -> Select[Any]:
    stmt = (
        select(models.Grade)
        .where(
            models.Grade.student_id == user_id,
            models.Grade.created_at >= start_date,
            models.Grade.created_at < end_date,
        )
        .order_by(models.Grade.created_at.desc())
    )
    return stmt


def _participation_statement(
    user_id: uuid.UUID | str, window_start: datetime, now: datetime
) -> Select[Any]:
    stmt = (
        select(
            models.Event.id,
            models.Event.title,
            models.Event.event_type,
            models.Event.starts_at,
            models.Event.ends_at,
        )
        .join(
            models.EventAttendance,
            models.EventAttendance.event_id == models.Event.id,
        )
        .where(
            models.EventAttendance.user_id == user_id,
            models.Event.is_active.is_(True),
            models.Event.starts_at >= window_start,
            models.Event.starts_at < now,
        )
        .order_by(models.Event.starts_at.desc())
    )
    return stmt


class UserStatsRepository(ReadOnlyRepository[models.User, UserDTO]):
    """Repository for User Statistics and Analytics."""

    @property
    def model(self) -> type[models.User]:
        return models.User

    @property
    def dto_class(self) -> type[UserDTO]:
        return UserDTO

    async def get_attendance_stats_raw(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        previous_start: datetime,
        now: datetime,
    ) -> Sequence[Any]:
        """Project window events and older user history in one scalar query.

        Disjoint indexed populations avoid a left-join OR over global history.
        There is no synthetic aggregate row when both populations are empty.
        """
        result = await self.db.execute(
            _attendance_statement(user_id, window_start, previous_start, now)
        )
        return result.all()

    async def get_grades(
        self,
        user_id: uuid.UUID | str,
        start_date: datetime,
        end_date: datetime,
    ) -> Sequence[models.Grade]:
        """Fetch the student's grades assigned in ``[start_date, end_date)``."""
        result = await self.db.execute(_grades_statement(user_id, start_date, end_date))
        return result.scalars().all()

    async def get_participation_stats_raw(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        now: datetime,
    ) -> list[ParticipationStatsDTO]:
        """Fetch registrations for the supplied half-open event window."""
        result = await self.db.execute(
            _participation_statement(user_id, window_start, now)
        )
        return [
            ParticipationStatsDTO(
                event_id=row.id,
                title=row.title,
                event_type=row.event_type,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
            )
            for row in result.all()
        ]

    async def get_summary_rows(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        previous_start: datetime,
        now: datetime,
        *,
        kinds: Collection[str],
    ) -> UserSummaryRows:
        # Explicitly typed NULLs keep compound-column result processors stable
        # and prevent PostgreSQL from resolving unused NULL slots to text.
        requested = set(kinds)
        unknown = requested - {"attendance", "grades", "participation"}
        if unknown:
            raise ValueError(f"Unknown summary kinds: {sorted(unknown)}")
        rows = UserSummaryRows()
        if not requested:
            return rows

        no_text = sql_cast(null(), String())
        no_date = sql_cast(null(), models.Event.starts_at.type)
        no_bool = sql_cast(null(), Boolean())
        no_float = sql_cast(null(), Float())
        no_uuid = sql_cast(null(), models.Event.id.type)
        statements: list[Select[Any]] = []
        if "attendance" in requested:
            attendance = _attendance_statement(
                user_id, window_start, previous_start, now
            ).subquery("attendance")
            statements.append(
                select(
                    literal("attendance").label("kind"),
                    attendance.c.starts_at.label("starts_at"),
                    attendance.c.title.label("title"),
                    attendance.c.registered_at.label("registered_at"),
                    attendance.c.is_registered.label("is_registered"),
                    no_float.label("score"),
                    no_uuid.label("event_id"),
                    no_text.label("event_type"),
                    no_date.label("ends_at"),
                )
            )
        if "grades" in requested:
            statements.append(
                _grades_statement(user_id, previous_start, now)
                .order_by(None)
                .with_only_columns(
                    literal("grades").label("kind"),
                    models.Grade.created_at.label("starts_at"),
                    models.Grade.subject.label("title"),
                    no_date.label("registered_at"),
                    no_bool.label("is_registered"),
                    models.Grade.score.label("score"),
                    no_uuid.label("event_id"),
                    no_text.label("event_type"),
                    no_date.label("ends_at"),
                    maintain_column_froms=True,
                )
            )
        if "participation" in requested:
            statements.append(
                _participation_statement(user_id, previous_start, now)
                .order_by(None)
                .with_only_columns(
                    literal("participation").label("kind"),
                    models.Event.starts_at.label("starts_at"),
                    models.Event.title.label("title"),
                    no_date.label("registered_at"),
                    no_bool.label("is_registered"),
                    no_float.label("score"),
                    models.Event.id.label("event_id"),
                    models.Event.event_type.label("event_type"),
                    models.Event.ends_at.label("ends_at"),
                    maintain_column_froms=True,
                )
            )

        packed = (
            statements[0].subquery("summary_rows")
            if len(statements) == 1
            else union_all(*statements).subquery("summary_rows")
        )
        result = await self.db.execute(
            select(packed).order_by(packed.c.starts_at.desc())
        )
        for row in result.mappings():
            starts_at = _as_utc(cast(datetime, row["starts_at"]))
            if row["kind"] == "attendance":
                registered_at = cast(datetime | None, row["registered_at"])
                rows.attendance.append(
                    UserAttendanceRow(
                        starts_at=starts_at,
                        title=cast(str | None, row["title"]),
                        registered_at=_as_utc(registered_at) if registered_at else None,
                        is_registered=bool(row["is_registered"]),
                    )
                )
            elif row["kind"] == "grades":
                rows.grades.append(
                    UserGradeRow(
                        created_at=starts_at,
                        subject=cast(str, row["title"]),
                        score=float(row["score"]),
                    )
                )
            else:
                rows.participation.append(
                    ParticipationStatsDTO(
                        event_id=cast(uuid.UUID, row["event_id"]),
                        title=cast(str, row["title"]),
                        event_type=cast(str | None, row["event_type"]),
                        starts_at=starts_at,
                        ends_at=_as_utc(cast(datetime, row["ends_at"])),
                    )
                )
        return rows
